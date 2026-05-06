"""
GET /api/stats — Aggregation analytics over bus_waypoints.

Cấu trúc tham khảo "Elasticsearch: The Definitive Guide" (chương 26–28):
  - terms bucket cho group-by (route, ignition)
  - metric aggregation lồng trong bucket (avg, max, min)
  - date_histogram cho time-series (cars sold over time → pings over time)
  - histogram cho phân bố numeric (speed distribution)
  - cardinality cho distinct count (xe đang hoạt động)

Endpoint trả về 1 metric duy nhất tuỳ tham số `metric`:
  - top_routes      : top N tuyến theo ping count + avg/max speed
  - speed_dist      : phân bố tốc độ theo bin 5 km/h
  - pings_per_min   : số ping/phút trong cửa sổ thời gian
  - vehicles_active : cardinality của trường vehicle
  - by_ignition     : số ping theo trạng thái nổ máy (true/false)
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from ..core.es_client import get_es, get_index

router = APIRouter()


MetricKind = Literal[
    "top_routes",
    "speed_dist",
    "pings_per_min",
    "vehicles_active",
    "by_ignition",
    "density",
]


@router.get("/stats")
def get_stats(
    metric: MetricKind = Query(default="top_routes",
                               description="Loại aggregation cần chạy."),
    from_:  str = Query(default="now-1h", alias="from"),
    to:     str = Query(default="now"),
    size:   int = Query(default=10, ge=1, le=100),
    interval: str = Query(default="1m",
                          description="Bước cho date_histogram (1m, 5m, 1h)."),
    precision: int = Query(default=11, ge=0, le=15,
                           description="Precision cho geotile_grid (0–15, ~11–13 cho TP.HCM)."),
):
    es = get_es()
    index = get_index()

    # Mọi metric đều áp time range trong filter context.
    base_filter = [{"range": {"@timestamp": {"gte": from_, "lte": to}}}]
    base_query  = {"bool": {"filter": base_filter}}

    # ── 1. Top routes by ping count + avg/max speed ────────────────────────────
    if metric == "top_routes":
        body = {
            "size": 0,
            "query": base_query,
            "aggs": {
                "by_route": {
                    "terms": {
                        "field": "route_no",
                        "size":  size,
                        "order": {"_count": "desc"},
                    },
                    "aggs": {
                        "avg_speed": {"avg": {"field": "speed"}},
                        "max_speed": {"max": {"field": "speed"}},
                        "min_speed": {"min": {"field": "speed"}},
                        # top_hits trong từng bucket → kèm route_name
                        "sample": {
                            "top_hits": {
                                "size": 1,
                                "_source": ["route_no", "route_name"],
                            }
                        },
                    },
                }
            },
        }
        resp = es.search(index=index, body=body)
        buckets = resp["aggregations"]["by_route"]["buckets"]
        return {
            "metric": metric,
            "took":   resp.get("took"),
            "window": {"from": from_, "to": to},
            "data": [
                {
                    "route_no":   b["key"],
                    "route_name": (b["sample"]["hits"]["hits"][0]["_source"].get("route_name", "")
                                   if b["sample"]["hits"]["hits"] else ""),
                    "pings":      b["doc_count"],
                    "avg_speed":  round(b["avg_speed"]["value"] or 0, 2),
                    "max_speed":  round(b["max_speed"]["value"] or 0, 2),
                    "min_speed":  round(b["min_speed"]["value"] or 0, 2),
                }
                for b in buckets
            ],
        }

    # ── 2. Speed distribution (histogram) ──────────────────────────────────────
    if metric == "speed_dist":
        body = {
            "size": 0,
            "query": base_query,
            "aggs": {
                "speed_bins": {
                    "histogram": {
                        "field":         "speed",
                        "interval":      5,
                        "min_doc_count": 0,
                        "extended_bounds": {"min": 0, "max": 80},
                    }
                }
            },
        }
        resp = es.search(index=index, body=body)
        buckets = resp["aggregations"]["speed_bins"]["buckets"]
        return {
            "metric": metric,
            "took":   resp.get("took"),
            "window": {"from": from_, "to": to},
            "data": [
                {"speed_bin": b["key"], "count": b["doc_count"]}
                for b in buckets
            ],
        }

    # ── 3. Pings per minute (date_histogram) ───────────────────────────────────
    if metric == "pings_per_min":
        body = {
            "size": 0,
            "query": base_query,
            "aggs": {
                "per_bucket": {
                    "date_histogram": {
                        "field":          "@timestamp",
                        "fixed_interval": interval,
                        "min_doc_count":  0,
                    },
                    "aggs": {
                        "active_vehicles": {
                            "cardinality": {"field": "vehicle"}
                        }
                    },
                }
            },
        }
        resp = es.search(index=index, body=body)
        buckets = resp["aggregations"]["per_bucket"]["buckets"]
        return {
            "metric":   metric,
            "took":     resp.get("took"),
            "interval": interval,
            "window":   {"from": from_, "to": to},
            "data": [
                {
                    "ts":               b["key_as_string"],
                    "pings":            b["doc_count"],
                    "active_vehicles":  b["active_vehicles"]["value"],
                }
                for b in buckets
            ],
        }

    # ── 4. Vehicles active (cardinality) ───────────────────────────────────────
    if metric == "vehicles_active":
        body = {
            "size": 0,
            "query": base_query,
            "aggs": {
                "vehicles":      {"cardinality": {"field": "vehicle"}},
                "routes_in_use": {"cardinality": {"field": "route_no"}},
                "total_pings":   {"value_count": {"field": "vehicle"}},
            },
        }
        resp = es.search(index=index, body=body)
        agg = resp["aggregations"]
        return {
            "metric": metric,
            "took":   resp.get("took"),
            "window": {"from": from_, "to": to},
            "data": {
                "vehicles_active": agg["vehicles"]["value"],
                "routes_in_use":   agg["routes_in_use"]["value"],
                "total_pings":     agg["total_pings"]["value"],
            },
        }

    # ── 5. Ping count theo trạng thái nổ máy ──────────────────────────────────
    if metric == "by_ignition":
        body = {
            "size": 0,
            "query": base_query,
            "aggs": {
                "by_ign": {
                    "terms": {"field": "ignition", "size": 2}
                }
            },
        }
        resp = es.search(index=index, body=body)
        buckets = resp["aggregations"]["by_ign"]["buckets"]
        return {
            "metric": metric,
            "took":   resp.get("took"),
            "window": {"from": from_, "to": to},
            "data": [
                {"ignition": bool(b["key"]), "pings": b["doc_count"]}
                for b in buckets
            ],
        }

    # ── 6. Density heatmap (geotile_grid + geo_centroid) ─────────────────────
    # Aggregation không gian: chia bản đồ thành các ô vuông theo precision Z,
    # mỗi ô trả về số ping + toạ độ trọng tâm các điểm trong ô.
    if metric == "density":
        body = {
            "size": 0,
            "query": base_query,
            "aggs": {
                "grid": {
                    "geotile_grid": {
                        "field":     "location",
                        "precision": precision,
                        "size":      5000,
                    },
                    "aggs": {
                        "center": {"geo_centroid": {"field": "location"}}
                    },
                }
            },
        }
        resp = es.search(index=index, body=body)
        buckets = resp["aggregations"]["grid"]["buckets"]
        points = []
        for b in buckets:
            loc = b.get("center", {}).get("location") or {}
            lat = loc.get("lat")
            lon = loc.get("lon")
            if lat is None or lon is None:
                continue
            points.append({
                "lat":   lat,
                "lon":   lon,
                "count": b["doc_count"],
                "tile":  b["key"],
            })
        return {
            "metric":    metric,
            "took":      resp.get("took"),
            "precision": precision,
            "window":    {"from": from_, "to": to},
            "data":      points,
        }

    raise HTTPException(status_code=400, detail=f"Unknown metric: {metric}")
