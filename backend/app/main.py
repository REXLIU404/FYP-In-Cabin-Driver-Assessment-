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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
