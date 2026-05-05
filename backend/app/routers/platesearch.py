from fastapi import APIRouter, Query
from ..core.es_client import get_es, get_index

router = APIRouter()


@router.get("/platesearch")
def search_plates(
    route_no: str = Query(default=""),
    size: int = Query(default=200, ge=1, le=500),
):
    es = get_es()
    index = get_index()

    filters = []
    if route_no.strip():
        filters.append({"term": {"route_no": route_no.strip()}})
    query = {"bool": {"filter": filters}} if filters else {"match_all": {}}

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
