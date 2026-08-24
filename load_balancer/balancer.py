from itertools import cycle
from typing import List, Dict
import threading
from collections import defaultdict


class Backend:
    def __init__(self, id: str, url: str, weight: int = 1):
        self.id = id
        self.url = url.rstrip("/")
        self.weight = weight
        self.healthy = True
        self.active_connections = 0
        self.total_requests = 0
        self.failed_requests = 0
        self.lock = threading.Lock()


class LoadBalancer:
    def __init__(self, backends: List[Dict], algorithm: str = "round_robin"):
        self.backends = [Backend(**b) for b in backends]
        self.algorithm = algorithm
        self._rr = cycle(self.backends)
        self._lock = threading.Lock()

    def get_healthy(self) -> List[Backend]:
        return [b for b in self.backends if b.healthy]

    def select(self) -> Backend | None:
        healthy = self.get_healthy()
        if not healthy:
            return None

        if self.algorithm == "least_connections":
            return min(healthy, key=lambda b: b.active_connections)

        # default: round-robin
        with self._lock:
            for _ in range(len(self.backends)):
                backend = next(self._rr)
                if backend.healthy:
                    return backend
        return None

    def mark_request_start(self, backend: Backend):
        with backend.lock:
            backend.active_connections += 1
            backend.total_requests += 1

    def mark_request_end(self, backend: Backend, success: bool = True):
        with backend.lock:
            backend.active_connections = max(0, backend.active_connections - 1)
            if not success:
                backend.failed_requests += 1
