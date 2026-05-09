"""
GET /api/nearby_buses, /api/nearby_stops

Find buses (and approximate stops) near an arbitrary (lat, lon) within a radius.

`nearby_buses`  — latest position per vehicle whose most recent ping is still
                  within `radius_m` of the query point, sorted by distance.

`nearby_stops`  — geohash_grid clusters of low-speed pings inside the radius,
                  treated as approximate stops (the dataset has no dedicated
                  stop index with coordinates). Centroid of each cluster is
                  returned as the stop point.
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


@router.get("/nearby_buses")
def nearby_buses(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
    radius_m: int = Query(500, ge=10, le=20000),
    from_: str = Query(default="now-1h", alias="from"),
    to: str = Query(default="now+3h"),
    max_vehicles: int = Query(default=300, ge=1, le=2000),
    route_no: str = Query(default=""),
):
    es = get_es()
    index = get_index()

    filters = [
        {"range": {"@timestamp": {"gte": from_, "lte": to}}},
        {
            "geo_distance": {
                "distance": f"{radius_m}m",
                "location": {"lat": lat, "lon": lon},
            }
        },
    ]
    if route_no:
        filters.append({"term": {"route_no": route_no}})

    body = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "by_vehicle": {
                "terms": {"field": "vehicle", "size": max_vehicles},
                "aggs": {
                    "latest": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"@timestamp": {"order": "desc"}}],
                            "_source": [
                                "vehicle", "lat", "lon", "speed", "heading",
                                "route_no", "route_name", "@timestamp",
                                "ignition", "aircon",
                            ],
                        }
                    }
                },
            }
        },
    }

    resp = es.search(index=index, body=body)
    buckets = resp["aggregations"]["by_vehicle"]["buckets"]

    features = []
    for b in buckets:
        hits = b["latest"]["hits"]["hits"]
        if not hits:
            continue
        src = hits[0]["_source"]
        v_lat, v_lon = src.get("lat"), src.get("lon")
        if v_lat is None or v_lon is None:
            continue

        # geo_distance filter only requires *some* ping in the window to be in
        # range — the latest one might have moved outside. Re-check.
        dist = _haversine_m(lat, lon, v_lat, v_lon)
        if dist > radius_m:
            continue

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [v_lon, v_lat]},
            "properties": {
                "vehicle":    src.get("vehicle", ""),
                "speed":      src.get("speed", 0),
                "heading":    src.get("heading", 0),
                "route_no":   src.get("route_no", ""),
                "route_name": src.get("route_name", ""),
                "timestamp":  src.get("@timestamp", ""),
                "ignition":   src.get("ignition", False),
                "aircon":     src.get("aircon", False),
                "lat":        v_lat,
                "lon":        v_lon,
                "distance_m": round(dist, 1),
            },
        })

    features.sort(key=lambda f: f["properties"]["distance_m"])

    return {
        "type": "FeatureCollection",
        "center": {"lat": lat, "lon": lon},
        "radius_m": radius_m,
        "count": len(features),
        "features": features,
    }


@router.get("/nearby_stops")
def nearby_stops(
    lat: float = Query(..., ge=-90.0, le=90.0),
    lon: float = Query(..., ge=-180.0, le=180.0),
    radius_m: int = Query(500, ge=10, le=20000),
    from_: str = Query(default="now-1h", alias="from"),
    to: str = Query(default="now+3h"),
    speed_max: float = Query(default=3.0, ge=0.0, le=20.0),
    precision: int = Query(default=8, ge=5, le=11),
    min_pings: int = Query(default=3, ge=1),
    size: int = Query(default=40, ge=1, le=200),
):
    es = get_es()
    index = get_index()

    body = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {"gte": from_, "lte": to}}},
                    {"range": {"speed": {"lte": speed_max}}},
                    {
                        "geo_distance": {
                            "distance": f"{radius_m}m",
                            "location": {"lat": lat, "lon": lon},
                        }
                    },
                ]
            }
        },
        "aggs": {
            "stops": {
                "geohash_grid": {
                    "field": "location",
                    "precision": precision,
                    "size": size,
                },
                "aggs": {
                    "centroid": {"geo_centroid": {"field": "location"}},
                    "vehicles": {"cardinality": {"field": "vehicle"}},
                    "routes": {"terms": {"field": "route_no", "size": 5}},
                },
            }
        },
    }

    resp = es.search(index=index, body=body)
    buckets = resp["aggregations"]["stops"]["buckets"]

    features = []
    for b in buckets:
        if b["doc_count"] < min_pings:
            continue
        c = b["centroid"]["location"]
        c_lat, c_lon = c["lat"], c["lon"]
        dist = _haversine_m(lat, lon, c_lat, c_lon)
        if dist > radius_m:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [c_lon, c_lat]},
            "properties": {
                "geohash":    b["key"],
                "lat":        c_lat,
                "lon":        c_lon,
                "pings":      b["doc_count"],
                "vehicles":   b["vehicles"]["value"],
                "routes":     [str(rb["key"]) for rb in b["routes"]["buckets"]],
                "distance_m": round(dist, 1),
            },
        })

    features.sort(key=lambda f: f["properties"]["distance_m"])

    return {
        "type": "FeatureCollection",
        "center": {"lat": lat, "lon": lon},
        "radius_m": radius_m,
        "count": len(features),
        "features": features,
    }
