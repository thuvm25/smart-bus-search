"""Utility functions for route mapping."""
import json
from pathlib import Path
from functools import lru_cache
from typing import Dict, Optional


# /app/app/core/route_mapping.py -> /app
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ROUTE_MAPPING_PATH = PROJECT_ROOT / "data" / "raw" / "vehicle_route_mapping.json"


@lru_cache(maxsize=1)
def load_route_mapping() -> Dict[str, dict]:
    """Load vehicle-to-route mapping from JSON file.

    Returns:
        Dict mapping vehicle ID to {'route_id': int, 'route_no': str}.
        Note: these values come from vehicle_route_mapping and are not
        assumed to be join keys for bus_routes/bus_stops datasets.
    """
    try:
        with open(ROUTE_MAPPING_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load route mapping: {e}")
        return {}


def get_route_info(vehicle_id: str) -> Optional[dict]:
    """Get route info for a vehicle ID.

    Args:
        vehicle_id: Vehicle hash ID

    Returns:
        {'route_id': int, 'route_no': str} or None if not found.
        This is a label lookup only.
    """
    mapping = load_route_mapping()
    return mapping.get(vehicle_id)
