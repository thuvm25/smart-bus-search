"""
GET /api/filter — Lọc bản ghi GPS theo nhiều thuộc tính (Filtering pure).

Mục tiêu: minh hoạ pattern bool.filter của Elasticsearch — kết hợp nhiều
mệnh đề term / range trong filter context (không tính _score, có cache).

Tham khảo "Elasticsearch: The Definitive Guide" chương 12 + 30:
  - filter context vs query context
  - bool.filter cho phép intersect bitset của nhiều clause
  - geo_bounding_box thuộc filter context, hoạt động cùng các filter khác

Endpoint trả về document raw (paginated) — không phải aggregation,
phục vụ trực quan hoá Discover-like.
"""

from fastapi import APIRouter, Query

from ..core.es_client import get_es, get_index

router = APIRouter()


@router.get("/filter")
def filter_waypoints(
    from_:        str = Query(default="now-1h", alias="from"),
    to:           str = Query(default="now"),
    route_no:     str = Query(default="", description="Khớp chính xác mã tuyến."),
    plate_no:     str = Query(default="", description="Khớp chính xác biển số."),
    vehicle:      str = Query(default="", description="Khớp chính xác vehicle hash."),
    ignition:     str = Query(default="", description="'true' hoặc 'false'."),
    speed_gte:    float | None = Query(default=None, ge=0, le=200),
    speed_lt:     float | None = Query(default=None, ge=0, le=200),
    bbox:         str = Query(default="",
                              description="Geo bbox: 'top_lat,left_lon,bottom_lat,right_lon'"),
    size:         int = Query(default=50,  ge=1, le=500),
    page:         int = Query(default=1,   ge=1, le=100),
    sort:         str = Query(default="desc", pattern="^(asc|desc)$"),
):
    """
    Mọi mệnh đề đều ở filter context để tận dụng query cache.
    Kết quả: documents (paginated) + tổng số hit + thời gian thực thi.
    """
    es = get_es()
    index = get_index()

    # ── Build filter clauses ──────────────────────────────────────────────────
    filters: list = [{"range": {"@timestamp": {"gte": from_, "lte": to}}}]

    if route_no.strip():
        filters.append({"term": {"route_no": route_no.strip()}})

    if plate_no.strip():
        filters.append({"term": {"plate_no": plate_no.strip()}})

    if vehicle.strip():
        filters.append({"term": {"vehicle": vehicle.strip()}})

    if ignition.lower() in ("true", "false"):
        filters.append({"term": {"ignition": ignition.lower() == "true"}})

    # Range trên speed — chỉ thêm clause khi có cận
    if speed_gte is not None or speed_lt is not None:
        rng: dict = {}
        if speed_gte is not None:
            rng["gte"] = speed_gte
        if speed_lt is not None:
            rng["lt"] = speed_lt
        filters.append({"range": {"speed": rng}})

    # Geo bounding box (lat,lon,lat,lon)
    if bbox.strip():
        try:
            parts = [float(x) for x in bbox.split(",")]
            if len(parts) == 4:
                top_lat, left_lon, bot_lat, right_lon = parts
                filters.append({
                    "geo_bounding_box": {
                        "location": {
                            "top_left":     {"lat": top_lat, "lon": left_lon},
                            "bottom_right": {"lat": bot_lat, "lon": right_lon},
                        }
                    }
                })
        except ValueError:
            pass  # bbox không hợp lệ → bỏ qua, không fail toàn request

    # ── Search body — pagination + sort by time ───────────────────────────────
    body = {
        "from":  (page - 1) * size,
        "size":  size,
        "query": {"bool": {"filter": filters}},
        "sort":  [{"@timestamp": {"order": sort}}],
        "_source": [
            "vehicle", "plate_no", "route_no", "route_name",
            "lat", "lon", "speed", "heading",
            "ignition", "aircon", "@timestamp",
        ],
        # track_total_hits=true để total chính xác kể cả khi > 10K
        "track_total_hits": True,
    }

    resp = es.search(index=index, body=body)

    hits = resp["hits"]["hits"]
    total = resp["hits"]["total"]["value"]

    return {
        "took":          resp.get("took"),
        "total":         total,
        "page":          page,
        "size":          size,
        "applied_filters": {
            "from":      from_,
            "to":        to,
            "route_no":  route_no or None,
            "plate_no":  plate_no or None,
            "vehicle":   vehicle or None,
            "ignition":  ignition or None,
            "speed_gte": speed_gte,
            "speed_lt":  speed_lt,
            "bbox":      bbox or None,
        },
        "data": [
            {
                "vehicle":    h["_source"].get("vehicle", ""),
                "plate_no":   h["_source"].get("plate_no", ""),
                "route_no":   h["_source"].get("route_no", ""),
                "route_name": h["_source"].get("route_name", ""),
                "lat":        h["_source"].get("lat"),
                "lon":        h["_source"].get("lon"),
                "speed":      h["_source"].get("speed"),
                "heading":    h["_source"].get("heading"),
                "ignition":   h["_source"].get("ignition"),
                "aircon":     h["_source"].get("aircon"),
                "timestamp":  h["_source"].get("@timestamp", ""),
            }
            for h in hits
        ],
    }
