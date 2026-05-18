"""
GET /api/fuzzysearch

Searches the bus_routes index (static reference data indexed by index_routes.py).
Supports fuzzy match on route name, route number, and stop names (both directions).
"""

import re

from fastapi import APIRouter, Query
from ..core.es_client import get_es

router = APIRouter()

ROUTES_INDEX = "bus_routes"


@router.get("/fuzzysearch")
def fuzzy_search(
    q: str = Query(default=""),
    size: int = Query(default=10, ge=1, le=50),
):
    es = get_es()

    if not q.strip():
        return {"query": q, "total": 0, "data": []}

    q_clean = q.strip()

    # Tách phần số và phần chữ ra riêng
    number_match = re.search(r'\b(\d+)\b', q_clean)
    only_text = re.sub(r'\b\d+\b', '', q_clean).strip()
    # Bỏ các từ prefix không có nghĩa trong search
    only_text = re.sub(r'\b(tuy[eê]n|s[oố]|xe\s*bu[yý]t)\b', '', only_text, flags=re.IGNORECASE).strip()

    def route_no_candidates(num: str) -> list:
        """Return [num, zero-padded] so "3" matches "03" and vice versa."""
        return list({num, num.zfill(2)})

    if number_match and only_text:
        # "tuyến 88 chợ rẫy" → filter by route_no + fuzzy match stop
        query = {
            "bool": {
                "must": [
                    {"terms": {"route_no": route_no_candidates(number_match.group(1))}}
                ],
                "should": [
                    {"match": {"stops_forward": {"query": only_text, "fuzziness": "AUTO"}}},
                    {"match": {"stops_return":  {"query": only_text, "fuzziness": "AUTO"}}},
                ],
            }
        }

    else:
        # "chợ rẫy", "bến thành" → fuzzy trên tên tuyến + trạm dừng
        # match_bool_prefix bổ sung auto-complete: token cuối được match theo prefix,
        # giúp "bệnh viện ch" vẫn khớp "Bệnh viện Chợ Rẫy"
        query = {
            "bool": {
                "should": [
                    {"match_phrase_prefix": {"route_name":    {"query": q_clean, "boost": 8}}},
                    {"match_phrase_prefix": {"stops_forward": {"query": q_clean, "boost": 6}}},
                    {"match_phrase_prefix": {"stops_return":  {"query": q_clean, "boost": 6}}},
                    {"match_phrase": {"stops_forward": {"query": q_clean, "boost": 5}}},
                    {"match_phrase": {"stops_return":  {"query": q_clean, "boost": 5}}},
                    {"match_phrase": {"route_name":    {"query": q_clean, "boost": 5}}},
                    {"match": {"route_name":    {"query": q_clean, "fuzziness": "AUTO", "prefix_length": 1, "boost": 2}}},
                    {"match": {"stops_forward": {"query": q_clean, "fuzziness": "AUTO", "prefix_length": 1}}},
                    {"match": {"stops_return":  {"query": q_clean, "fuzziness": "AUTO", "prefix_length": 1}}},
                    {"match_bool_prefix": {"route_name":    {"query": q_clean, "boost": 2}}},
                    {"match_bool_prefix": {"stops_forward": {"query": q_clean}}},
                    {"match_bool_prefix": {"stops_return":  {"query": q_clean}}},
                ],
                "minimum_should_match": 1,
            }
        }

    body = {
        "size": size,
        "query": query,
        # Highlight returns the matching stop name with empty tags → clean string
        "highlight": {
            "pre_tags": [""],
            "post_tags": [""],
            "fields": {
                "stops_forward": {"number_of_fragments": 1},
                "stops_return": {"number_of_fragments": 1},
            },
        },
        "_source": ["route_no", "route_name", "fare", "schedule"],
    }

    resp = es.search(index=ROUTES_INDEX, body=body)
    hits = resp["hits"]["hits"]
    total = resp["hits"]["total"]["value"]

    results = []
    for hit in hits:
        src = hit["_source"]
        highlights = hit.get("highlight", {})

        # Pick the first matching stop from either direction
        matched_stop = ""
        for field in ("stops_forward", "stops_return"):
            frags = highlights.get(field)
            if frags:
                matched_stop = frags[0].strip()
                break

        results.append({
            "route_no":    src.get("route_no", ""),
            "route_name":  src.get("route_name", ""),
            "matched_stop": matched_stop,
            "fare":        src.get("fare", ""),
            "schedule":    src.get("schedule", ""),
        })

    return {"query": q, "total": total, "data": results}
