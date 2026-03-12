from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from elasticsearch import Elasticsearch

from ..dependencies import get_es_client, get_index_name

router = APIRouter()


class NearbyRequest(BaseModel):
    center: dict
    radius_m: int = 500
    time_window_minutes: int | None = None
    limit: int | None = None


class ActiveRequest(BaseModel):
    minutes: int = 0  # 0 = no time filter (all data, for historical dataset)


class VehicleTraceRequest(BaseModel):
    vehicle: str
    time_window_minutes: int = 0  # 0 = no time filter (all history, for static/past data)


# --------------- helpers ---------------

def _nearby_query(index: str, lat: float, lon: float, radius_m: int,
                  minutes: int | None, limit: int, es: Elasticsearch) -> dict:
    filters: list[dict] = [
        {"geo_distance": {"distance": f"{radius_m}m", "location": {"lat": lat, "lon": lon}}},
    ]
    if minutes is not None and minutes > 0:
        filters.append({"range": {"datetime": {"gte": f"now-{minutes}m"}}})

    body = {
        "size": limit,
        "query": {"bool": {"filter": filters}},
        "sort": [
            {"datetime": {"order": "desc", "unmapped_type": "date"}},
            {"_geo_distance": {"location": {"lat": lat, "lon": lon}, "order": "asc", "unit": "m"}},
        ],
        "collapse": {"field": "vehicle"},
        "aggs": {"unique_vehicles": {"cardinality": {"field": "vehicle"}}},
    }

    resp = es.search(index=index, **body)
    hits = resp["hits"]["hits"]
    unique = resp["aggregations"]["unique_vehicles"]["value"]

    items = []
    for h in hits:
        src = h["_source"]
        loc = src.get("location", {})
        items.append({
            "vehicle": src.get("vehicle"),
            "datetime": src.get("datetime"),
            "x": loc.get("lon"),
            "y": loc.get("lat"),
            "speed": src.get("speed"),
            "ignition": src.get("ignition"),
            "aircon": src.get("aircon"),
            "heading": src.get("heading"),
            "route_id": src.get("route_id"),
            "route_no": src.get("route_no"),
        })

    return {
        "items": items,
        "lat": lat,
        "lon": lon,
        "radius_m": radius_m,
        "total": unique,
        "returned": len(items),
        "limit": limit,
    }


# --------------- endpoints ---------------

@router.get("/nearby")
async def nearby_get(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_m: int = Query(500, ge=50, le=50_000),
    minutes: int | None = Query(None, ge=0),
    limit: int = Query(200, ge=1, le=5000),
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    return _nearby_query(index, lat, lon, radius_m, minutes, limit, es)


@router.post("/nearby")
async def nearby_post(
    req: NearbyRequest,
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    lat = req.center.get("lat", 0)
    lon = req.center.get("lon", 0)
    limit = min(req.limit or 200, 5000)
    return _nearby_query(index, lat, lon, req.radius_m, req.time_window_minutes, limit, es)


@router.post("/active")
async def active_buses(
    req: ActiveRequest,
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    """Latest position per vehicle. minutes=0 means no time filter (all data, for historical dataset)."""
    filters: list[dict] = []
    if req.minutes > 0:
        filters.append({"range": {"datetime": {"gte": f"now-{req.minutes}m"}}})

    query: dict = {"match_all": {}} if not filters else {"bool": {"filter": filters}}

    body = {
        "size": 1000,
        "query": query,
        "sort": [{"datetime": {"order": "desc", "unmapped_type": "date"}}],
        "collapse": {"field": "vehicle"},
    }
    resp = es.search(index=index, **body)

    items = []
    for h in resp["hits"]["hits"]:
        src = h["_source"]
        loc = src.get("location", {})
        items.append({
            "vehicle": src.get("vehicle"),
            "datetime": src.get("datetime"),
            "lat": loc.get("lat"),
            "lon": loc.get("lon"),
            "speed": src.get("speed"),
            "ignition": src.get("ignition"),
            "route_id": src.get("route_id"),
            "route_no": src.get("route_no"),
        })

    return {"items": items, "total": len(items)}


@router.post("/vehicle-trace")
async def vehicle_trace(
    req: VehicleTraceRequest,
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    """GPS trace for one vehicle. time_window_minutes=0 means full history (for historical data)."""
    filters: list[dict] = [{"term": {"vehicle": req.vehicle}}]
    if req.time_window_minutes > 0:
        filters.append({"range": {"datetime": {"gte": f"now-{req.time_window_minutes}m"}}})

    body = {
        "size": 10_000,
        "query": {"bool": {"filter": filters}},
        "sort": [{"datetime": "asc"}],
    }
    resp = es.search(index=index, **body)

    items = []
    for h in resp["hits"]["hits"]:
        src = h["_source"]
        loc = src.get("location", {})
        items.append({
            "datetime": src.get("datetime"),
            "lat": loc.get("lat"),
            "lon": loc.get("lon"),
            "speed": src.get("speed"),
            "ignition": src.get("ignition"),
        })

    return {"items": items, "total": len(items), "vehicle": req.vehicle}
