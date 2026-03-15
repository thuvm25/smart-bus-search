"""Pydantic schemas for API request/response validation.

These schemas mirror the Elasticsearch mapping in models/mapping.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class GeoPoint(BaseModel):
    lat: float
    lon: float


class BusWaypoint(BaseModel):
    vehicle: str
    datetime: datetime
    location: GeoPoint
    speed: Optional[float] = None
    ignition: Optional[bool] = None
    heading: Optional[float] = None
    aircon: Optional[bool] = None
    door_up: Optional[bool] = None
    door_down: Optional[bool] = None
    working: Optional[bool] = None
    driver: Optional[str] = None
    route_id: Optional[str] = None
    route_no: Optional[str] = None
    route_name: Optional[str] = None
    stop_name: Optional[str] = None


class NearbySearchResponse(BaseModel):
    items: list[dict]
    lat: float
    lon: float
    radius_m: int
    total: int = 0
    returned: int = 0
    limit: int = 0
