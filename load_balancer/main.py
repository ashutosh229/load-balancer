from fastapi import (
    FastAPI,
    Request,
    Response,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
import httpx
import time
import json
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

# WebSocket support
import websockets
from websockets.exceptions import ConnectionClosed

from .balancer import LoadBalancer
from .health import start_health_checker
from .metrics import MetricsCollector

# Load config
with open(Path(__file__).parent.parent / "config" / "backends.json") as f:
    cfg = json.load(f)

lb = LoadBalancer(cfg["backends"], algorithm=cfg.get("algorithm", "round_robin"))
metrics = MetricsCollector()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # start background health checks
    start_health_checker(
        lb,
        cfg.get("health_check_path", "/health"),
        cfg.get("health_check_interval", 5),
    )
    yield


app = FastAPI(title="Messaging Load Balancer", lifespan=lifespan)


# ------------------------------------------------------------------
# LB management endpoints  ← MUST be registered FIRST
# ------------------------------------------------------------------
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


# ----------------------------------------------------------------------
# WebSocket reverse proxy  (NEW)
# ----------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_proxy(client_ws: WebSocket):
    await client_ws.accept()

    backend = lb.select()
    if backend is None:
        await client_ws.close(code=1013)  # Try again later
        return

    # Convert http:// → ws://
    backend_ws_url = backend.url.replace("http://", "ws://").replace(
        "https://", "wss://"
    )
    target = f"{backend_ws_url}/ws"

    lb.mark_request_start(backend)
    start = time.perf_counter()

    try:
        async with websockets.connect(target) as server_ws:

            async def client_to_backend():
                try:
                    while True:
                        data = await client_ws.receive_text()
                        await server_ws.send(data)
                except (WebSocketDisconnect, ConnectionClosed):
                    pass

            async def backend_to_client():
                try:
                    while True:
                        data = await server_ws.recv()
                        await client_ws.send_text(data)
                except (WebSocketDisconnect, ConnectionClosed):
                    pass

            # Run both directions until one side closes
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(client_to_backend()),
                    asyncio.create_task(backend_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

        success = True
    except Exception as e:
        print(f"[WS] proxy error → {backend.id}: {e}")
        success = False
        try:
            await client_ws.close(code=1011)
        except Exception:
            pass
    finally:
        elapsed = (time.perf_counter() - start) * 1000
        metrics.record(backend.id, elapsed, 101 if success else 500, success)
        lb.mark_request_end(backend, success)


# ----------------------------------------------------------------------
# HTTP reverse proxy (your original code, kept almost unchanged)
# ----------------------------------------------------------------------
@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def proxy(request: Request, path: str):
    backend = lb.select()
    if backend is None:
        raise HTTPException(status_code=503, detail="No healthy backends")

    target = f"{backend.url}/{path}"
    if request.url.query:
        target += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)  # let httpx set the correct Host

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

        # Filter hop-by-hop headers
        excluded = {
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection",
        }
        response_headers = {
            k: v for k, v in resp.headers.items() if k.lower() not in excluded
        }

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=response_headers,
            media_type=resp.headers.get("content-type"),
        )
    except Exception as e:
        lb.mark_request_end(backend, success=False)
        metrics.record(backend.id, (time.perf_counter() - start) * 1000, 502, False)
        raise HTTPException(status_code=502, detail=str(e))
