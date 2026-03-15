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


def search_nearby(lat: float, lon: float, radius_m: int = 500, limit: int | None = None) -> dict:
    """Search for nearby buses using GET."""
    params = {"lat": lat, "lon": lon, "radius_m": radius_m}
    if limit is not None:
        params["limit"] = limit
    return get_json("search/nearby", params)


def search_active(minutes: int = 0) -> dict:
    """Search for active buses. minutes=0 means all time (historical data)."""
    return post_json("search/active", {"minutes": minutes})


def search_vehicle_trace(vehicle: str, minutes: int = 0, timeout_sec: int = 60) -> dict:
    """Get GPS trace for a vehicle. minutes=0 means full history. Can take 30–60s for large traces."""
    payload = {"vehicle": vehicle, "time_window_minutes": minutes}
    resp = requests.post(_url("search/vehicle-trace"), json=payload, timeout=timeout_sec)
    resp.raise_for_status()
    return resp.json()


def get_analytics_stats() -> dict:
    """Index stats (doc count, etc.)."""
    return get_json("analytics/stats")


def get_analytics_density(precision: int = 5, minutes: int | None = None) -> dict:
    """Geohash grid density."""
    params = {"precision": precision}
    if minutes is not None:
        params["minutes"] = minutes
    return get_json("analytics/density", params=params)


def get_analytics_active_count(minutes: int = 5) -> dict:
    """Active vehicles count in last N minutes."""
    return get_json("analytics/active-count", params={"minutes": minutes})


def get_analytics_speed(minutes: int | None = None) -> dict:
    """Speed statistics."""
    params = {} if minutes is None else {"minutes": minutes}
    return get_json("analytics/speed", params=params)


def run_benchmark(timeout_sec: int = 120) -> dict:
    """Run benchmark suite (indexing, search, aggregation). Can take 1–2 minutes."""
    resp = requests.post(_url("benchmark/run"), json={}, timeout=timeout_sec)
    resp.raise_for_status()
    return resp.json()

