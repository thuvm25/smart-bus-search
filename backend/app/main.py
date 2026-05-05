"""
Smart Bus GPS — FastAPI Backend
Wraps Elasticsearch queries and exposes a clean REST API
that mirrors all Kibana dashboard panels.

Run:
    uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

Docs:
    http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import fuzzysearch, livebus, platesearch, routedetail
from .core.es_client import get_es, get_index, ES_HOST

app = FastAPI(
    title="Smart Bus GPS API",
    description=(
        "Real-time bus GPS dashboard API — queries Elasticsearch index "
        "`bus_waypoints` and exposes metrics, time-series, speed, routes, "
        "vehicle trajectories, and live positions."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow Streamlit (and any dev tool) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(livebus.router,     prefix="/api", tags=["LiveBus"])
app.include_router(fuzzysearch.router, prefix="/api", tags=["FuzzySearch"])
app.include_router(platesearch.router,  prefix="/api", tags=["PlateSearch"])
app.include_router(routedetail.router,  prefix="/api", tags=["RouteDetail"])


# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health():
    """Check API and Elasticsearch connectivity."""
    try:
        es = get_es()
        cluster = es.cluster.health()
        es_status = cluster.get("status", "unknown")
        es_ok = es_status in ("green", "yellow")
    except Exception as exc:
        return {
            "api": "ok",
            "elasticsearch": "error",
            "detail": str(exc),
            "index": get_index(),
            "es_host": ES_HOST,
        }

    return {
        "api": "ok",
        "elasticsearch": es_status,
        "index": get_index(),
        "es_host": ES_HOST,
    }


@app.get("/", tags=["Health"])
def root():
    return {
        "message": "Smart Bus GPS API",
        "docs": "/docs",
        "health": "/health",
        "endpoints": [
            "/api/fuzzysearch",
            "/api/livebus",
        ],
    }
