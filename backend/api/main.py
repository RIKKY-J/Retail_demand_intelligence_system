"""FastAPI application entry point with CORS configuration and router registration."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import (
    alerts,
    analytics,
    evaluation,
    forecasts,
    inventory,
    overview,
)
from backend.src.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI-Powered Retail Inventory & Demand Intelligence API",
    version="1.0.0",
    lifespan=lifespan,
    description=(
        "REST API serving M5-formatted demand forecasts, simulated inventory state, "
        "forecast-aware safety stock & replenishment recommendations, analytics, and "
        "28-day policy backtest metrics."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(overview.router)
app.include_router(inventory.router)
app.include_router(forecasts.router)
app.include_router(analytics.router)
app.include_router(alerts.router)
app.include_router(evaluation.router)
