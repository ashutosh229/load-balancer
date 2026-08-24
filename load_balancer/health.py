"""
Background health checker for load balancer backends.

Periodically probes each backend's health endpoint and updates
the Backend.healthy flag used by the selection algorithm.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from balancer import LoadBalancer

logger = logging.getLogger("load_balancer.health")


async def _check_one(client: httpx.AsyncClient, backend, path: str) -> bool:
    """Return True if backend responds successfully to the health probe."""
    url = f"{backend.url}{path}"
    try:
        resp = await client.get(url, timeout=2.0)
        return 200 <= resp.status_code < 400
    except Exception as exc:
        logger.debug("Health check failed for %s: %s", backend.id, exc)
        return False


async def _health_loop(
    lb: "LoadBalancer",
    path: str,
    interval: float,
) -> None:
    """Continuously mark backends healthy / unhealthy."""
    async with httpx.AsyncClient() as client:
        while True:
            for backend in lb.backends:
                was_healthy = backend.healthy
                backend.healthy = await _check_one(client, backend, path)
                if was_healthy != backend.healthy:
                    state = "healthy" if backend.healthy else "unhealthy"
                    logger.info("Backend %s is now %s", backend.id, state)
            await asyncio.sleep(interval)


def start_health_checker(
    lb: "LoadBalancer",
    path: str = "/health",
    interval: float = 5.0,
) -> asyncio.Task:
    """
    Spawn a background asyncio task that periodically health-checks
    every registered backend.

    Returns the Task so the caller can cancel it on shutdown if desired.
    """
    logger.info(
        "Starting health checker (path=%s, interval=%.1fs) for %d backends",
        path,
        interval,
        len(lb.backends),
    )
    task = asyncio.create_task(_health_loop(lb, path, interval))
    return task
