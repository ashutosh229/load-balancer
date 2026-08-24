from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
import httpx
import time
import json
from pathlib import Path
from contextlib import asynccontextmanager
from balancer import LoadBalancer
from health import start_health_checker
from metrics import MetricsCollector

# Load config
with open(Path(__file__).parent.parent / "config" / "backends.json") as f:
    cfg = json.load(f)

lb = LoadBalancer(cfg["backends"], algorithm=cfg.get("algorithm", "round_robin"))
metrics = MetricsCollector()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # start background health checks
    start_health_checker(
        lb, cfg.get("health_check_path", "/health"), cfg.get("health_check_interval", 5)
    )
    yield


app = FastAPI(title="Messaging Load Balancer", lifespan=lifespan)


@app.api_route(
    "/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
)
async def proxy(request: Request, path: str):
    backend = lb.select()
    if backend is None:
        raise HTTPException(status_code=503, detail="No healthy backends")

    target = f"{backend.url}/{path}"
    if request.url.query:
        target += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)  # let httpx set it

    body = await request.body()
    start = time.perf_counter()
    lb.mark_request_start(backend)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method=request.method,
                url=target,
                headers=headers,
                content=body,
            )
        success = 200 <= resp.status_code < 500
        elapsed = (time.perf_counter() - start) * 1000  # ms
        metrics.record(backend.id, elapsed, resp.status_code, success)
        lb.mark_request_end(backend, success)

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers),
            media_type=resp.headers.get("content-type"),
        )
    except Exception as e:
        lb.mark_request_end(backend, success=False)
        metrics.record(backend.id, (time.perf_counter() - start) * 1000, 502, False)
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/lb/health")
async def lb_health():
    return {
        "status": "ok",
        "healthy_backends": [b.id for b in lb.get_healthy()],
        "algorithm": lb.algorithm,
    }


@app.get("/lb/metrics")
async def get_metrics():
    return metrics.snapshot(lb)
