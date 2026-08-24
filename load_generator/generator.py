# load_generator/generator.py
import asyncio
import httpx
import time
import statistics
from collections import defaultdict
import json


async def worker(client, url, results, duration):
    end = time.time() + duration
    while time.time() < end:
        start = time.perf_counter()
        try:
            r = await client.get(url)  # or POST to a messaging endpoint
            latency = (time.perf_counter() - start) * 1000
            results.append({"ok": True, "latency": latency, "status": r.status_code})
        except Exception:
            results.append(
                {"ok": False, "latency": (time.perf_counter() - start) * 1000}
            )


async def run_load(target: str, concurrency: int, duration: int = 30):
    results = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = [
            asyncio.create_task(worker(client, target, results, duration))
            for _ in range(concurrency)
        ]
        await asyncio.gather(*tasks)

    latencies = [r["latency"] for r in results if r["ok"]]
    total = len(results)
    success = sum(1 for r in results if r["ok"])
    rps = total / duration
    summary = {
        "target": target,
        "concurrency": concurrency,
        "duration": duration,
        "total_requests": total,
        "successful": success,
        "error_rate": 1 - (success / total) if total else 0,
        "rps": rps,
        "latency_avg_ms": statistics.mean(latencies) if latencies else None,
        "latency_p50": statistics.median(latencies) if latencies else None,
        "latency_p95": (
            statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else None
        ),
        "latency_p99": (
            statistics.quantiles(latencies, n=100)[98] if len(latencies) > 100 else None
        ),
    }
    return summary
