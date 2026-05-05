"""
GET /api/positions
Returns: latest GPS position per vehicle as GeoJSON FeatureCollection.
Mirror: Kibana Maps — "📍 Bus Positions (Live Map)" (bus-live-map),
        top_hits scalingType — 1 point per vehicle, colored by speed.
"""

from fastapi import APIRouter, Query
from ..core.es_client import get_es, get_index

router = APIRouter()


@router.get("/livebus")
def get_positions(
    from_: str = Query(default="now-1h", alias="from"),
    to: str = Query(default="now"),
    max_vehicles: int = Query(default=200, ge=1, le=2000),
    route_no: str = Query(default=""),
    plate_no: str = Query(default=""),
):
    es = get_es()
    index = get_index()

    filters = [{"range": {"@timestamp": {"gte": from_, "lte": to}}}]
    if route_no:
        filters.append({"term": {"route_no": route_no}})
    if plate_no:
        filters.append({"term": {"plate_no": plate_no}})

    body = {
        "size": 0,
        "query": {
            "bool": {"filter": filters}
        },
        "aggs": {
            "by_vehicle": {
                "terms": {
                    "field": "vehicle",
                    "size": max_vehicles,
                },
                "aggs": {
                    "latest": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"@timestamp": {"order": "desc"}}],
                            "_source": [
                                "vehicle", "lat", "lon", "speed", "heading",
                                "route_no", "route_name", "plate_no", "@timestamp",
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
        lat = src.get("lat")
        lon = src.get("lon")
        if lat is None or lon is None:
            continue

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat],
            },
            "properties": {
                "vehicle":    src.get("vehicle", ""),
                "speed":      src.get("speed", 0),
                "heading":    src.get("heading", 0),
                "route_no":   src.get("route_no", ""),
                "route_name": src.get("route_name", ""),
                "plate_no":   src.get("plate_no", ""),
                "timestamp":  src.get("@timestamp", ""),
                "ignition":   src.get("ignition", False),
                "aircon":     src.get("aircon", False),
                "lat":        lat,
                "lon":        lon,
            },
        })

    return {
        "type": "FeatureCollection",
        "count": len(features),
        "features": features,
    }
