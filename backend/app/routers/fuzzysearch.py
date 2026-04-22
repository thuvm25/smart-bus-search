"""
GET /api/routes

"""

from fastapi import APIRouter, Query
from ..core.es_client import get_es, get_index

router = APIRouter()


@router.get("/fuzzysearch")
def get_routes(
    from_: str = Query(default="now-1h", alias="from"),
    to: str = Query(default="now"),
    size: int = Query(default=20, ge=1, le=100),
    q: str = Query(default=""),  # fuzzy/wildcard search term
):
    es = get_es()
    index = get_index()

    # Build query filter
    filters: list = [
        {"range": {"@timestamp": {"gte": from_, "lte": to}}},
        {"exists": {"field": "route_name.keyword"}},
    ]
    if len(q.strip()) >= 1:
        q_clean = q.strip()
        should_clauses: list = [
            {
                "wildcard": {
                    "route_name.keyword": {
                        "value": f"*{q_clean}*",
                        "case_insensitive": True,
                    }
                }
            }
        ]
        if q_clean.isdigit():
            should_clauses.append({"term": {"route_no": int(q_clean)}})
        filters.append({"bool": {"should": should_clauses, "minimum_should_match": 1}})

    body = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "top_routes": {
                "terms": {
                    "field": "route_name.keyword",
                    "size": size,
                    "order": {"_count": "desc"},
                },
                "aggs": {
                    "route_no": {
                        "terms": {"field": "route_no", "size": 1}
                    }
                },
            }
        },
    }

    resp = es.search(index=index, body=body)
    buckets = resp["aggregations"]["top_routes"]["buckets"]

    return {
        "query": q,
        "total": len(buckets),
        "data": [
            {
                "route_name": b["key"],
                "route_no": (
                    b["route_no"]["buckets"][0]["key"]
                    if b["route_no"]["buckets"] else ""
                ),
                "pings": b["doc_count"],
            }
            for b in buckets
        ],
    }
