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


def search_active(minutes: int) -> dict:
    """Search for active buses in the last N minutes."""
    payload = {"time_window_minutes": minutes}
    return post_json("search/active", payload)


def search_vehicle_trace(vehicle: str, minutes: int) -> dict:
    """Get GPS trace for a specific vehicle."""
    payload = {"vehicle": vehicle, "time_window_minutes": minutes}
    return post_json("search/vehicle-trace", payload)

