"""
GET /api/most_active_bus, /api/bus_track

`most_active_bus`  — vehicles ranked by ping count in a short recent window
                     (default: last 5 minutes), with their latest position
                     and average/max speed.

`bus_track`        — full ordered trajectory of a single vehicle within a
                     longer window (default: last 1 hour), with cumulative
                     distance and speed summary.
"""

from math import asin, cos, radians, sin, sqrt

from fastapi import APIRouter, Query

from ..core.es_client import get_es, get_index

router = APIRouter()


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * R * asin(sqrt(a))


@router.get("/most_active_bus")
def most_active_bus(
    from_: str = Query(default="now-5m", alias="from"),
    to: str = Query(default="now"),
    size: int = Query(default=10, ge=1, le=100),
):
    es = get_es()
    index = get_index()

    body = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [{"range": {"@timestamp": {"gte": from_, "lte": to}}}]
            }
        },
        "aggs": {
            "by_vehicle": {
                "terms": {
                    "field": "vehicle",
                    "size": size,
                    "order": {"_count": "desc"},
                },
                "aggs": {
                    "avg_speed": {"avg": {"field": "speed"}},
                    "max_speed": {"max": {"field": "speed"}},
                    "latest": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"@timestamp": {"order": "desc"}}],
                            "_source": [
                                "vehicle", "plate_no", "lat", "lon", "speed", "heading",
                                "route_no", "route_name", "@timestamp",
                            ],
                        }
                    },
                },
            }
        },
    }

    resp = es.search(index=index, body=body)
    buckets = resp["aggregations"]["by_vehicle"]["buckets"]

    data = []
    for b in buckets:
        hits = b["latest"]["hits"]["hits"]
        if not hits:
            continue
        src = hits[0]["_source"]
        lat, lon = src.get("lat"), src.get("lon")
        if lat is None or lon is None:
            continue
        data.append({
            "vehicle":    src.get("vehicle", b["key"]),
            "plate_no":   src.get("plate_no", ""),
            "pings":      b["doc_count"],
            "avg_speed":  round(b["avg_speed"]["value"] or 0, 1),
            "max_speed":  round(b["max_speed"]["value"] or 0, 1),
            "lat":        lat,
            "lon":        lon,
            "route_no":   src.get("route_no", ""),
            "route_name": src.get("route_name", ""),
            "timestamp":  src.get("@timestamp", ""),
            "heading":    src.get("heading", 0),
        })

    return {"from": from_, "to": to, "count": len(data), "data": data}


@router.get("/bus_track")
def bus_track(
    vehicle: str = Query(..., min_length=1),
    from_: str = Query(default="now-1h", alias="from"),
    to: str = Query(default="now"),
    max_points: int = Query(default=2000, ge=10, le=10000),
):
    es = get_es()
    index = get_index()

    body = {
        "size": max_points,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"vehicle": vehicle}},
                    {"range": {"@timestamp": {"gte": from_, "lte": to}}},
                ]
            }
        },
        "sort": [{"@timestamp": {"order": "asc"}}],
        "_source": [
            "vehicle", "lat", "lon", "speed", "heading",
            "route_no", "route_name", "@timestamp",
        ],
    }

    resp = es.search(index=index, body=body)
    hits = resp["hits"]["hits"]

    points = []
    total_dist = 0.0
    sum_speed = 0.0
    max_speed = 0.0
    n_speed = 0
    prev_lat = prev_lon = None
    route_no = route_name = ""

    for h in hits:
        s = h["_source"]
        lat, lon = s.get("lat"), s.get("lon")
        if lat is None or lon is None:
            continue
        sp = s.get("speed", 0) or 0
        if prev_lat is not None:
            total_dist += _haversine_m(prev_lat, prev_lon, lat, lon)
        prev_lat, prev_lon = lat, lon
        sum_speed += sp
        n_speed += 1
        if sp > max_speed:
            max_speed = sp
        points.append({
            "lat":       lat,
            "lon":       lon,
            "speed":     sp,
            "heading":   s.get("heading", 0),
            "timestamp": s.get("@timestamp", ""),
        })
        if not route_no and s.get("route_no"):
            route_no = s["route_no"]
        if not route_name and s.get("route_name"):
            route_name = s["route_name"]

    avg_speed = round(sum_speed / n_speed, 1) if n_speed else 0.0

    return {
        "vehicle":          vehicle,
        "from":             from_,
        "to":               to,
        "count":            len(points),
        "route_no":         route_no,
        "route_name":       route_name,
        "total_distance_m": round(total_dist, 1),
        "avg_speed":        avg_speed,
        "max_speed":        round(max_speed, 1),
        "points":           points,
    }
