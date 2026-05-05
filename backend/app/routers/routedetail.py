from fastapi import APIRouter, Query
from ..core.es_client import get_es

ROUTES_INDEX = "bus_routes"

router = APIRouter()


@router.get("/routedetail")
def get_route_detail(
    route_no: str = Query(default=""),
    size: int = Query(default=50, ge=1, le=200),
):
    es = get_es()

    if route_no.strip():
        body = {
            "size": 1,
            "query": {"term": {"route_no": route_no.strip()}},
        }
        resp = es.search(index=ROUTES_INDEX, body=body)
        hits = resp["hits"]["hits"]
        if not hits:
            return {"data": [], "total": 0}
        return {"data": [hits[0]["_source"]], "total": 1}

    body = {
        "size": size,
        "query": {"match_all": {}},
        "sort": [{"route_no": {"order": "asc"}}],
    }
    resp = es.search(index=ROUTES_INDEX, body=body)
    hits = resp["hits"]["hits"]
    return {
        "data": [h["_source"] for h in hits],
        "total": resp["hits"]["total"]["value"],
    }
