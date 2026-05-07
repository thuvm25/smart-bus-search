from fastapi import APIRouter, Query
from ..core.es_client import get_es, get_index

router = APIRouter()


@router.get("/platesearch")
def search_plates(
    route_no: str = Query(default=""),
    from_:   str = Query(default="now-1h", alias="from"),
    to:      str = Query(default="now"),
    size:    int = Query(default=200, ge=1, le=500),
):
    """
    Liệt kê biển số xe duy nhất trong cửa sổ thời gian, có thể lọc theo
    tuyến. Time range mặc định là `now-1h..now` để tránh quét toàn bộ
    index — terms aggregation trên `plate_no` không có time filter sẽ
    timeout khi index lớn (~30M+ doc).
    """
    es = get_es()
    index = get_index()

    filters = [{"range": {"@timestamp": {"gte": from_, "lte": to}}}]
    if route_no.strip():
        filters.append({"term": {"route_no": route_no.strip()}})
    query = {"bool": {"filter": filters}}

    body = {
        "size": 0,
        "query": query,
        "aggs": {
            "plates": {
                "terms": {"field": "plate_no", "size": size, "order": {"_key": "asc"}},
                "aggs": {
                    "latest": {
                        "top_hits": {
                            "size": 1,
                            "sort": [{"@timestamp": {"order": "desc"}}],
                            "_source": ["plate_no", "vehicle", "route_no", "route_name"],
                        }
                    }
                },
            }
        },
    }

    resp = es.search(index=index, body=body)
    results = []
    for bucket in resp["aggregations"]["plates"]["buckets"]:
        hits = bucket["latest"]["hits"]["hits"]
        if not hits:
            continue
        src = hits[0]["_source"]
        results.append({
            "plate_no":   src.get("plate_no", ""),
            "vehicle":    src.get("vehicle", ""),
            "route_no":   src.get("route_no", ""),
            "route_name": src.get("route_name", ""),
        })

    return {"data": results, "total": len(results)}
