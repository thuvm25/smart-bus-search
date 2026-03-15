"""Lookup nearest bus stop name from waypoint coordinates."""
from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional


def _project_root() -> Path:
    """Resolve project root: /app in Docker, or repo root locally."""
    env_root = os.getenv("PROJECT_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parent.parent.parent


BUS_STOPS_PATH = _project_root() / "bus_stops.json"
MAX_MATCH_DISTANCE_M = 300.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in meters."""
    r = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


@lru_cache(maxsize=1)
def load_stops() -> list[dict]:
    """Load stop catalog from bus_stops.json."""
    try:
        with open(BUS_STOPS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [
            s
            for s in data
            if s.get("lat") is not None and s.get("lng") is not None and s.get("stop_name")
        ]
    except Exception as e:
        print(f"Warning: Could not load bus stops from {BUS_STOPS_PATH}: {e}")
        return []


def get_nearest_stop_name(lat: float, lon: float) -> Optional[str]:
    """Return nearest stop_name if within matching threshold."""
    if lat is None or lon is None:
        return None
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None

    stops = load_stops()
    if not stops:
        return None

    best_name: Optional[str] = None
    best_distance = float("inf")

    for stop in stops:
        d = _haversine_m(lat_f, lon_f, float(stop["lat"]), float(stop["lng"]))
        if d < best_distance:
            best_distance = d
            best_name = str(stop["stop_name"])

    if best_distance <= MAX_MATCH_DISTANCE_M:
        return best_name
    return None
