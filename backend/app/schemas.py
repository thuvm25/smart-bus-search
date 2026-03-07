from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BusWaypoint(BaseModel):
    vehicle: str
    datetime: datetime
    x: float
    y: float
    ignition: Optional[bool] = None
    heading: Optional[float] = None
    aircon: Optional[bool] = None
    door_up: Optional[bool] = None
    door_down: Optional[bool] = None
    route_name: Optional[str] = None
    stop_name: Optional[str] = None
    # Values from vehicle_route_mapping only (not guaranteed to match bus_routes keys)
    mapping_route_id: Optional[int] = None
    mapping_route_no: Optional[str] = None


class NearbySearchResponse(BaseModel):
    items: list[BusWaypoint]
    lat: float
    lon: float
    radius_m: int
    total: int = 0
    returned: int = 0
    limit: int = 0

