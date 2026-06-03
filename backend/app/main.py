"""FastAPI application entry point (API Gateway).

Run from the backend/ directory:
    uvicorn app.main:app --reload --port 8000
Swagger UI: http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  (register ORM models on Base)
from .db import Base, engine
from .routers import export, risk, sessions, status, windows


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="In-Cabin Driver Risk Assessment API",
    version="0.1.0",
    description="Backend skeleton: session CRUD, late-fusion risk scoring (MockAIProvider), SQLite persistence, JSON/CSV export.",
    lifespan=lifespan,
)

# Allow the local frontend to call the API in FYP2 (frontend stays on
# localStorage by default in FYP1; this does not change the prototype).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (
    sessions.router,
    windows.router,
    risk.router,
    status.router,
    export.router,
):
    app.include_router(r)


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
