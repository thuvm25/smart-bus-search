from __future__ import annotations

import unicodedata
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from elasticsearch import Elasticsearch

from ..dependencies import get_es_client, get_index_name
from ..core.route_mapping import get_route_info

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


class TextSearchRequest(BaseModel):
    q: str
    minutes: int | None = None
    limit: int = 200


# --------------- helpers ---------------

def _fold_text(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return " ".join(s.split())

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
        vehicle_id = src.get("vehicle")
        # On-the-fly enrich for UI: route metadata (cheap, dict lookup) if missing.
        route_id = src.get("route_id")
        route_no = src.get("route_no")
        route_name = src.get("route_name")
        if vehicle_id and (route_id is None or route_no is None or route_name is None):
            info = get_route_info(str(vehicle_id))
            if info:
                route_id = route_id or (str(info.get("route_id")) if info.get("route_id") is not None else None)
                route_no = route_no or info.get("route_no")
                route_name = route_name or info.get("route_name")

        items.append({
            "vehicle": vehicle_id,
            "datetime": src.get("datetime"),
            "x": loc.get("lon"),
            "y": loc.get("lat"),
            "speed": src.get("speed"),
            "ignition": src.get("ignition"),
            "aircon": src.get("aircon"),
            "heading": src.get("heading"),
            "route_id": route_id,
            "route_no": route_no,
            "route_name": route_name,
            "stop_name": src.get("stop_name"),
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
        vehicle_id = src.get("vehicle")
        route_id = src.get("route_id")
        route_no = src.get("route_no")
        route_name = src.get("route_name")
        if vehicle_id and (route_id is None or route_no is None or route_name is None):
            info = get_route_info(str(vehicle_id))
            if info:
                route_id = route_id or (str(info.get("route_id")) if info.get("route_id") is not None else None)
                route_no = route_no or info.get("route_no")
                route_name = route_name or info.get("route_name")

        items.append({
            "vehicle": vehicle_id,
            "datetime": src.get("datetime"),
            "lat": loc.get("lat"),
            "lon": loc.get("lon"),
            "speed": src.get("speed"),
            "ignition": src.get("ignition"),
            "route_id": route_id,
            "route_no": route_no,
            "route_name": route_name,
            "stop_name": src.get("stop_name"),
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


@router.get("/text")
async def text_search_get(
    q: str = Query(..., min_length=1, description="Free text query (route/stop/vehicle/route_no)"),
    minutes: int | None = Query(None, ge=0),
    limit: int = Query(200, ge=1, le=2000),
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    filters: list[dict] = []
    if minutes is not None and minutes > 0:
        filters.append({"range": {"datetime": {"gte": f"now-{minutes}m"}}})

    folded_q = _fold_text(q)
    # Search both original (accented) and folded (no-accent) fields.
    text_query = {
        "bool": {
            "should": [
                {
                    "multi_match": {
                        "query": q,
                        "fields": ["route_name^3", "stop_name^3"],
                        "type": "best_fields",
                        "operator": "and",
                        "fuzziness": "AUTO",
                    }
                },
                {
                    "multi_match": {
                        "query": folded_q,
                        "fields": ["route_name_folded^2", "stop_name_folded^2"],
                        "type": "best_fields",
                        "operator": "and",
                        "fuzziness": "AUTO",
                    }
                },
            ],
            "minimum_should_match": 1,
        }
    }
    should_exact = [
        {"term": {"vehicle": q}},
        {"term": {"route_no": q}},
        {"term": {"route_id": q}},
    ]

    body = {
        "size": limit,
        "query": {
            "bool": {
                "filter": filters,
                "must": [text_query],
                "should": should_exact,
            }
        },
        "sort": [{"datetime": {"order": "desc", "unmapped_type": "date"}}],
        "highlight": {"fields": {"route_name": {}, "stop_name": {}}},
    }

    resp = es.search(index=index, **body)
    hits = resp["hits"]["hits"]

    items = []
    for h in hits:
        src = h["_source"]
        loc = src.get("location", {})
        items.append(
            {
                "vehicle": src.get("vehicle"),
                "datetime": src.get("datetime"),
                "lat": loc.get("lat"),
                "lon": loc.get("lon"),
                "speed": src.get("speed"),
                "ignition": src.get("ignition"),
                "route_id": src.get("route_id"),
                "route_no": src.get("route_no"),
                "route_name": src.get("route_name"),
                "stop_name": src.get("stop_name"),
                "highlight": h.get("highlight", {}),
            }
        )

    return {
        "q": q,
        "items": items,
        "total": int(resp["hits"]["total"]["value"]),
        "returned": len(items),
        "limit": limit,
        "minutes": minutes,
    }
