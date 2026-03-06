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


class NearbySearchResponse(BaseModel):
    items: list[BusWaypoint]
    lat: float
    lon: float
    radius_m: int

