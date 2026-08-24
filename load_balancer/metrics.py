"""
In-memory metrics collector for the messaging load balancer.

Tracks per-backend request counts, success/failure rates, and latency
percentiles. Exposed via GET /lb/metrics.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from balancer import LoadBalancer


@dataclass
class BackendStats:
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    status_codes: Dict[int, int] = field(default_factory=lambda: defaultdict(int))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, latency_ms: float, status_code: int, success: bool) -> None:
        with self.lock:
            self.request_count += 1
            if success:
                self.success_count += 1
            else:
                self.failure_count += 1
            self.latencies_ms.append(latency_ms)
            # Keep a bounded window to avoid unbounded memory growth
            if len(self.latencies_ms) > 10_000:
                self.latencies_ms = self.latencies_ms[-5_000:]
            self.status_codes[status_code] += 1

    def summary(self) -> Dict[str, Any]:
        with self.lock:
            lats = sorted(self.latencies_ms)
            n = len(lats)

            def percentile(p: float) -> float | None:
                if n == 0:
                    return None
                idx = min(int(n * p / 100), n - 1)
                return round(lats[idx], 2)

            return {
                "request_count": self.request_count,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "error_rate": (
                    round(self.failure_count / self.request_count, 4)
                    if self.request_count
                    else 0.0
                ),
                "latency_avg_ms": (round(sum(lats) / n, 2) if n else None),
                "latency_p50_ms": percentile(50),
                "latency_p95_ms": percentile(95),
                "latency_p99_ms": percentile(99),
                "status_codes": dict(self.status_codes),
            }


class MetricsCollector:
    def __init__(self) -> None:
        self._stats: Dict[str, BackendStats] = defaultdict(BackendStats)
        self._start_time = time.time()
        self._global_lock = threading.Lock()

    def record(
        self,
        backend_id: str,
        latency_ms: float,
        status_code: int,
        success: bool,
    ) -> None:
        self._stats[backend_id].record(latency_ms, status_code, success)

    def snapshot(self, lb: "LoadBalancer") -> Dict[str, Any]:
        """Return a JSON-serialisable metrics snapshot including live backend state."""
        uptime = round(time.time() - self._start_time, 1)
        backends = {}
        for b in lb.backends:
            stats = self._stats[b.id].summary()
            backends[b.id] = {
                "url": b.url,
                "healthy": b.healthy,
                "weight": b.weight,
                "active_connections": b.active_connections,
                "total_requests": b.total_requests,
                "failed_requests": b.failed_requests,
                **stats,
            }

        total_requests = sum(s["request_count"] for s in backends.values())
        total_success = sum(s["success_count"] for s in backends.values())
        total_failure = sum(s["failure_count"] for s in backends.values())

        return {
            "uptime_seconds": uptime,
            "algorithm": lb.algorithm,
            "total_requests": total_requests,
            "total_success": total_success,
            "total_failure": total_failure,
            "overall_error_rate": (
                round(total_failure / total_requests, 4) if total_requests else 0.0
            ),
            "backends": backends,
        }
