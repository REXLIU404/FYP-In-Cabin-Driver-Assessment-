"""FastAPI application entry point (API Gateway).

Run from the backend/ directory:
    uvicorn app.main:app --reload --port 8000
Swagger UI: http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import models  # noqa: F401  (register ORM models on Base)
from .db import initialize_database
from .config import settings
from .routers import export, faults, risk, sessions, status, windows


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="In-Cabin Driver Risk Assessment API",
    version="0.1.0",
    description="Trained MobileNetV3 ONNX + XGBoost inference, temporal fusion, SQLite sessions and replay mode.",
    lifespan=lifespan,
)

# Local development uses a Vite proxy; explicit origins also allow direct API use.
# ``expose_headers``: across origins a page can read only the CORS-safelisted response headers,
# so without this the front end would never see ``X-DRA-Backend`` on a direct (non-proxied)
# call and would take every error answer of this backend for a proxy's. Same-origin needs nothing.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[faults.BACKEND_HEADER],
)


class BackendMarkerMiddleware:
    """Stamp ``X-DRA-Backend: 1`` on every response this application sends.

    When nothing listens on the backend's port, the Vite dev proxy answers ``/api`` calls with
    an HTTP 500 of its own (empty plain-text body). Without a mark that answer is
    indistinguishable from the backend's own 500 (``model_runtime``), so the dashboard reported
    "a model or storage error on the server" for a backend that was simply not running. The
    front end treats an error answer WITHOUT this header as "the backend did not answer".

    Added after CORS, so it is the outermost user middleware: preflight answers and static
    ``dist/`` files are marked too. One response is out of its reach - the unhandled-exception
    500, which ServerErrorMiddleware sends from outside every user middleware - and is marked
    in ``routers.faults.on_unhandled_exception``.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_marked(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[faults.BACKEND_HEADER] = faults.BACKEND_HEADER_VALUE
            await send(message)

        await self.app(scope, receive, send_marked)


app.add_middleware(BackendMarkerMiddleware)

for r in (
    sessions.router,
    windows.router,
    risk.router,
    status.router,
    export.router,
    faults.router,
):
    app.include_router(r)

# Make the /infer failures the route itself cannot see (schema 422, stray exceptions)
# observable. Responses are unchanged; see routers/faults.py.
faults.install_exception_handlers(app)


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/models", tags=["health"])
def models_status():
    from .providers.trained import get_provider, ModelUnavailable
    try:
        return {"models_loaded": True, **get_provider().info}
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


# After `npm run build`, one local server serves both API and production UI.
_dist = Path(__file__).resolve().parents[2] / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
