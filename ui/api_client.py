from __future__ import annotations

import os

import requests
from dotenv import load_dotenv


load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")

# For API endpoints, ensure we have /api prefix
API_BASE_URL = f"{BACKEND_URL}/api"


def _url(path: str) -> str:
    """Build full API URL."""
    return f"{API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def get_json(path: str, params: dict = None) -> dict:
    """GET request to API."""
    resp = requests.get(_url(path), params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def post_json(path: str, payload: dict) -> dict:
    """POST request to API."""
    resp = requests.post(_url(path), json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ─── Search ──────────────────────────────────────────────────────────

def search_nearby(lat: float, lon: float, radius_m: int = 500, limit: int | None = None) -> dict:
    """Search for nearby buses using GET."""
    params = {"lat": lat, "lon": lon, "radius_m": radius_m}
    if limit is not None:
        params["limit"] = limit
    return get_json("search/nearby", params)


def search_active(minutes: int = 0) -> dict:
    """Search for active buses. minutes=0 means all time (historical data)."""
    return post_json("search/active", {"minutes": minutes})


def search_vehicle_trace(vehicle: str, minutes: int = 0) -> dict:
    """Get GPS trace for a vehicle. minutes=0 means full history (historical data)."""
    payload = {"vehicle": vehicle, "time_window_minutes": minutes}
    return post_json("search/vehicle-trace", payload)


def search_text(q: str, minutes: int | None = None, limit: int = 200) -> dict:
    """Fuzzy text search across route_name/stop_name (and exact route_no/vehicle)."""
    params = {"q": q, "limit": limit}
    if minutes is not None:
        params["minutes"] = minutes
    return get_json("search/text", params)


# ─── Analytics ───────────────────────────────────────────────────────

def get_density(precision: int = 5, minutes: int | None = None) -> dict:
    """Get bus density per geohash cell (heatmap data)."""
    params = {"precision": precision}
    if minutes is not None:
        params["minutes"] = minutes
    return get_json("analytics/density", params)


def get_speed_stats(minutes: int | None = None) -> dict:
    """Get speed statistics (min/avg/max/histogram)."""
    params = {}
    if minutes is not None:
        params["minutes"] = minutes
    return get_json("analytics/speed", params)


def get_active_count(minutes: int = 5) -> dict:
    """Get number of distinct active vehicles in last N minutes."""
    return get_json("analytics/active-count", {"minutes": minutes})


def get_index_stats() -> dict:
    """Get basic index-level statistics."""
    return get_json("analytics/stats")


def get_realtime(window_seconds: int = 60) -> dict:
    """Get realtime ingest metrics for the last N seconds."""
    return get_json("analytics/realtime", {"window_seconds": window_seconds})


def run_benchmark() -> dict:
    """Run benchmarks via backend (backend has ES access).

    Uses a longer timeout since benchmark can take 10-30+ seconds.
    """
    resp = requests.post(_url("benchmark/run"), json={}, timeout=120)
    resp.raise_for_status()
    return resp.json()
