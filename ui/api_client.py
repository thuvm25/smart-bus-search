from __future__ import annotations

import os

import requests
from dotenv import load_dotenv


load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")


def search_nearby(lat: float, lon: float, radius_m: int = 500) -> dict:
    url = f"{BACKEND_URL}/api/search/nearby"
    params = {"lat": lat, "lon": lon, "radius_m": radius_m}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()



import os
from typing import Any, Dict

import requests


BASE_URL = os.getenv("BUSGPS_API_BASE_URL", "http://localhost:8000/api")


def _url(path: str) -> str:
    return f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    resp = requests.post(_url(path), json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def search_nearby(center_lat: float, center_lon: float, radius_m: int, minutes: int):
    payload = {
        "center": {"lat": center_lat, "lon": center_lon},
        "radius_m": radius_m,
        "time_window_minutes": minutes,
    }
    return post_json("search/nearby", payload)


def search_active(minutes: int):
    payload = {"time_window_minutes": minutes}
    return post_json("search/active", payload)


def search_vehicle_trace(vehicle: str, minutes: int):
    payload = {"vehicle": vehicle, "time_window_minutes": minutes}
    return post_json("search/vehicle-trace", payload)

