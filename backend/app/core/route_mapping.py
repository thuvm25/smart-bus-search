"""Utility functions for route mapping."""
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional


def _project_root() -> Path:
    """Resolve project root: /app in Docker, or repo root locally."""
    env_root = os.getenv("PROJECT_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parent.parent.parent


ROUTE_MAPPING_PATH = _project_root() / "data" / "raw" / "vehicle_route_mapping.json"
BUS_ROUTES_PATH = _project_root() / "bus_routes.json"


@lru_cache(maxsize=1)
def load_route_mapping() -> Dict[str, dict]:
    """Load vehicle-to-route mapping from JSON file.

    Returns:
        Dict mapping vehicle ID to {'route_id': int, 'route_no': str}.
    """
    try:
        with open(ROUTE_MAPPING_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load route mapping from {ROUTE_MAPPING_PATH}: {e}")
        return {}


@lru_cache(maxsize=1)
def load_bus_routes() -> Dict[int, dict]:
    """Load bus routes indexed by bus_id.

    Returns:
        Dict mapping bus_id to {'bus_no': str, 'route_name': str}.
    """
    try:
        with open(BUS_ROUTES_PATH, 'r', encoding='utf-8') as f:
            rows = json.load(f)

        out: Dict[int, dict] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            bus_id = row.get("bus_id")
            try:
                bus_id_int = int(bus_id)
            except (TypeError, ValueError):
                continue
            out[bus_id_int] = {
                "bus_no": row.get("bus_no"),
                "route_name": row.get("route_name"),
            }
        return out
    except Exception as e:
        print(f"Warning: Could not load bus_routes from {BUS_ROUTES_PATH}: {e}")
        return {}


def get_route_info(vehicle_id: str) -> Optional[dict]:
    """Get route info for a vehicle ID."""
    base = load_route_mapping().get(vehicle_id)
    if not isinstance(base, dict):
        return None

    route_id = base.get("route_id")
    try:
        route_id_int = int(route_id)
    except (TypeError, ValueError):
        route_id_int = None

    route_name = None
    if route_id_int is not None:
        route_meta = load_bus_routes().get(route_id_int)
        if isinstance(route_meta, dict):
            route_name = route_meta.get("route_name")

    return {
        "route_id": route_id_int,
        "route_no": base.get("route_no"),
        "route_name": route_name,
    }
