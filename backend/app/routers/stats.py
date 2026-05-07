"""
GET /api/stats — Aggregation analytics over bus_waypoints index.

Endpoint trả 1 metric duy nhất tuỳ tham số `metric`:
  - top_routes      : top N tuyến theo số xe + avg/max/min speed
  - top_jam_routes  : top N tuyến kẹt nhất (% ping speed<5)
  - traffic_jam     : tỷ lệ kẹt + breakdown 4 nhóm jam/slow/normal/fast
  - pings_per_min   : số xe duy nhất theo phút, phân theo trạng thái di chuyển
  - vehicles_active : cardinality(vehicle), cardinality(route), value_count
  - speed_by_hour   : avg(speed, missing=0) theo giờ trong 24h

Tất cả metric chấp nhận cùng bộ filter dimension như /api/livebus
(route_no, plate_no, ignition, speed_gte/lt, time range) — agg luôn được
scope theo bool.filter để dashboard nhất quán giữa các panel.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from ..core.es_client import get_es, get_index

router = APIRouter()

ROUTES_INDEX = "bus_routes"


def _fill_route_names(es, items: list) -> list:
    """
    Bù route_name cho các item có route_name trống.
    Dataset gốc lệch leading-zero: vehicle có route_no="1" không match
    routes_clean.json (chứa "01"). Hàm này lookup `bus_routes` index với
    cả 2 dạng (padded + lstrip 0) rồi gán lại.
    """
    missing = [it for it in items if not it.get("route_name")]
    if not missing:
        return items

    # Build danh sách route_no cần tra (cả 2 dạng)
    candidates: set = set()
    for it in missing:
        rn = str(it.get("route_no", "")).strip()
        if rn:
            candidates.add(rn)
            candidates.add(rn.zfill(2))                  # "1" → "01"
            candidates.add(rn.lstrip("0") or "0")        # "01" → "1"

    try:
        resp = es.search(index=ROUTES_INDEX, body={
            "size": len(candidates),
            "query": {"terms": {"route_no": list(candidates)}},
            "_source": ["route_no", "route_name"],
        })
    except Exception:
        return items  # bus_routes có thể chưa được index → bỏ qua

    name_map = {h["_source"]["route_no"]: h["_source"].get("route_name", "")
                for h in resp["hits"]["hits"]}

    for it in missing:
        rn = str(it.get("route_no", "")).strip()
        it["route_name"] = (
            name_map.get(rn)
            or name_map.get(rn.zfill(2))
            or name_map.get(rn.lstrip("0") or "0")
            or ""
        )
    return items


MetricKind = Literal[
    "top_routes",
    "pings_per_min",
    "vehicles_active",
    "traffic_jam",
    "top_jam_routes",
    "speed_by_hour",
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
    # ── filter params (đồng bộ với /api/livebus) ───────────────────────────
    route_no:  str = Query(default=""),
    plate_no:  str = Query(default=""),
    ignition:  str = Query(default="", description="'true'/'false'/''"),
    speed_gte: float | None = Query(default=None, ge=0, le=200),
    speed_lt:  float | None = Query(default=None, ge=0, le=200),
):
    es = get_es()
    index = get_index()

    # Mọi metric đều áp time range + các filter dimension khác trong filter context.
    base_filter: list = [{"range": {"@timestamp": {"gte": from_, "lte": to}}}]
    if route_no:
        base_filter.append({"term": {"route_no": route_no}})
    if plate_no:
        base_filter.append({"term": {"plate_no": plate_no}})
    if ignition.lower() in ("true", "false"):
        base_filter.append({"term": {"ignition": ignition.lower() == "true"}})
    if speed_gte is not None or speed_lt is not None:
        rng: dict = {}
        if speed_gte is not None:
            rng["gte"] = speed_gte
        if speed_lt is not None:
            rng["lt"] = speed_lt
        base_filter.append({"range": {"speed": rng}})

    base_query = {"bool": {"filter": base_filter}}

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
                        "avg_speed":         {"avg": {"field": "speed"}},
                        "max_speed":         {"max": {"field": "speed"}},
                        "min_speed":         {"min": {"field": "speed"}},
                        # cardinality → số xe DUY NHẤT của tuyến (không phải số ping)
                        "vehicles_on_route": {"cardinality": {"field": "vehicle"}},
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
        items = [
            {
                "route_no":   b["key"],
                "route_name": (b["sample"]["hits"]["hits"][0]["_source"].get("route_name", "")
                               if b["sample"]["hits"]["hits"] else ""),
                "pings":      b["doc_count"],
                "vehicles":   b["vehicles_on_route"]["value"],
                "avg_speed":  round(b["avg_speed"]["value"] or 0, 2),
                "max_speed":  round(b["max_speed"]["value"] or 0, 2),
                "min_speed":  round(b["min_speed"]["value"] or 0, 2),
            }
            for b in buckets
        ]
        return {
            "metric": metric,
            "took":   resp.get("took"),
            "window": {"from": from_, "to": to},
            "data":   _fill_route_names(es, items),
        }

    # ── 2. Pings per minute — phân loại trạng thái theo dải tốc độ ────────────
    # Lưu ý: dataset gốc không có speed=0 (GPS device clamp tối thiểu = 1.0).
    # Xe đang dừng đèn đỏ / dừng trạm thực ra báo speed = 1-4 km/h do GPS noise.
    # Phân nhóm:
    #   - moving   : speed ≥ 5         (đang di chuyển thật)
    #   - stopped  : 1 ≤ speed < 5    (dừng đèn đỏ / dừng trạm)
    #   - all      : tất cả ping      (kể cả speed=null = đỗ depot)
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
                        "moving": {
                            "filter": {"range": {"speed": {"gte": 5}}},
                            "aggs": {"vehs": {"cardinality": {"field": "vehicle"}}},
                        },
                        "stopped": {
                            "filter": {"range": {"speed": {"gte": 0, "lt": 5}}},
                            "aggs": {"vehs": {"cardinality": {"field": "vehicle"}}},
                        },
                        "active_vehicles": {
                            "cardinality": {"field": "vehicle"}
                        },
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
                    "ts":              b["key_as_string"],
                    "pings":           b["doc_count"],
                    "moving":          b["moving"]["vehs"]["value"],
                    "stopped":         b["stopped"]["vehs"]["value"],
                    "active_vehicles": b["active_vehicles"]["value"],
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

    # ── 4. Tỷ lệ kẹt xe — % ping có speed < 5 km/h ────────────────────────────
    # Dùng `range` aggregation chia 2 bucket: kẹt (<5 km/h) vs di chuyển (≥5).
    # Không phải mọi ping <5 km/h là kẹt — có thể là dừng đèn đỏ, dừng trạm.
    # Nhưng tỷ lệ này tỉ lệ thuận với mức độ ùn tắc, dùng làm proxy chỉ số kẹt.
    if metric == "traffic_jam":
        body = {
            "size": 0,
            "query": base_query,
            "aggs": {
                "speed_buckets": {
                    "range": {
                        "field": "speed",
                        "ranges": [
                            {"key": "jam",   "from": 0,  "to": 5},
                            {"key": "slow",  "from": 5,  "to": 15},
                            {"key": "normal","from": 15, "to": 40},
                            {"key": "fast",  "from": 40},
                        ],
                    }
                },
                "total":    {"value_count": {"field": "speed"}},
                "avg_speed":{"avg":         {"field": "speed"}},
            },
        }
        resp = es.search(index=index, body=body)
        agg     = resp["aggregations"]
        buckets = agg["speed_buckets"]["buckets"]
        total   = agg["total"]["value"] or 0

        by_key = {b["key"]: b["doc_count"] for b in buckets}
        jam_pct = (by_key.get("jam", 0) / total * 100) if total else 0

        return {
            "metric": metric,
            "took":   resp.get("took"),
            "window": {"from": from_, "to": to},
            "data": {
                "total_pings": total,
                "avg_speed":   round(agg["avg_speed"]["value"] or 0, 2),
                "jam_pings":   by_key.get("jam", 0),
                "slow_pings":  by_key.get("slow", 0),
                "normal_pings":by_key.get("normal", 0),
                "fast_pings":  by_key.get("fast", 0),
                "jam_pct":     round(jam_pct, 1),
            },
        }

    # ── 7b. Top N tuyến kẹt nhất (% ping speed<5 cao nhất) ─────────────────
    # Pattern: terms agg + filter sub-agg + bucket_sort pipeline.
    # Mỗi bucket route trả về:
    #   - total ping
    #   - jam ping (speed < 5)
    #   - jam_pct = jam / total
    # Sau đó dùng bucket_sort để sort theo jam_pct desc.
    if metric == "top_jam_routes":
        body = {
            "size": 0,
            "query": base_query,
            "aggs": {
                "by_route": {
                    "terms": {
                        "field": "route_no",
                        # Lấy top 50 tuyến đông xe nhất trước, rồi mới sort
                        # theo jam_pct ở pipeline — tránh tuyến nhỏ <100 ping
                        # bị nhiễu (vd 10 ping toàn kẹt → 100% jam).
                        "size":  50,
                    },
                    "aggs": {
                        "total":   {"value_count": {"field": "speed"}},
                        "jam":     {"filter": {"range": {"speed": {"lt": 5}}}},
                        "avg_speed": {"avg": {"field": "speed"}},
                        "vehicles":  {"cardinality": {"field": "vehicle"}},
                        "sample":  {
                            "top_hits": {"size": 1, "_source": ["route_no", "route_name"]}
                        },
                        # Tỷ lệ jam được tính qua bucket_script (pipeline agg)
                        "jam_pct": {
                            "bucket_script": {
                                "buckets_path": {
                                    "jam":   "jam._count",
                                    "total": "total.value",
                                },
                                "script": "params.total > 0 ? (params.jam / params.total * 100) : 0",
                            }
                        },
                        # Sắp xếp lại các bucket theo jam_pct desc, lấy top size
                        "sort_jam": {
                            "bucket_sort": {
                                "sort": [{"jam_pct": "desc"}],
                                "size": size,
                            }
                        },
                    },
                }
            },
        }
        resp = es.search(index=index, body=body)
        buckets = resp["aggregations"]["by_route"]["buckets"]
        items = [
            {
                "route_no":  b["key"],
                "route_name": (b["sample"]["hits"]["hits"][0]["_source"].get("route_name", "")
                               if b["sample"]["hits"]["hits"] else ""),
                "total":     b["total"]["value"],
                "jam_pings": b["jam"]["doc_count"],
                "jam_pct":   round(b["jam_pct"]["value"], 1),
                "avg_speed": round(b["avg_speed"]["value"] or 0, 2),
                "vehicles":  b["vehicles"]["value"],
            }
            for b in buckets
        ]
        return {
            "metric": metric,
            "took":   resp.get("took"),
            "window": {"from": from_, "to": to},
            "data":   _fill_route_names(es, items),
        }

    # ── 8. Tốc độ trung bình theo giờ trong ngày ──────────────────────────────
    # date_histogram theo giờ + avg(speed) — giúp nhận diện giờ cao điểm:
    # avg_speed thấp → giờ kẹt; avg_speed cao → giờ thoáng.
    if metric == "speed_by_hour":
        # Dataset gốc bỏ qua field `speed` cho ping của xe đang đỗ tại
        # depot (minimal payload mode). Để chart phản ánh đúng "fleet
        # average" bao gồm xe đỗ, dùng `missing: 0` — coi ping không
        # có speed như speed=0. Cách này không bỏ doc nào, kết quả
        # smooth: giờ buýt vận hành ~20 km/h, giờ xe đỗ tụt gần 0.
        body = {
            "size": 0,
            "query": base_query,
            "aggs": {
                "by_hour": {
                    "date_histogram": {
                        "field":             "@timestamp",
                        "calendar_interval": "1h",
                        "min_doc_count":     0,
                    },
                    "aggs": {
                        "avg_speed":   {"avg": {"field": "speed", "missing": 0}},
                        "active_vehs": {"cardinality": {"field": "vehicle"}},
                    },
                }
            },
        }
        resp = es.search(index=index, body=body)
        buckets = resp["aggregations"]["by_hour"]["buckets"]
        return {
            "metric": metric,
            "took":   resp.get("took"),
            "window": {"from": from_, "to": to},
            "data": [
                {
                    "ts":            b["key_as_string"],
                    "pings":         b["doc_count"],
                    "avg_speed":     round(b["avg_speed"]["value"] or 0, 2),
                    "active_vehs":   b["active_vehs"]["value"],
                }
                for b in buckets
            ],
        }

    raise HTTPException(status_code=400, detail=f"Unknown metric: {metric}")
