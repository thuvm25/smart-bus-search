"""
Index bus routes from routes_clean.json into Elasticsearch.

Creates index 'bus_routes' and bulk-indexes all valid routes.
Designed to support fuzzy search by route name, stop names, and other fields.

Usage:
    ES_HOST=http://localhost:9200 python scripts/index_routes.py

Environment variables:
    ES_HOST      – Elasticsearch base URL (default: http://localhost:9200)
    ROUTES_FILE  – path to routes_clean.json (default: data/raw/routes_clean.json)
    ES_INDEX     – index name (default: bus_routes)
    RECREATE     – "true" to drop and recreate the index (default: false)
"""

import json
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

ES_HOST      = os.getenv("ES_HOST", "http://localhost:9200")
ROUTES_FILE  = os.getenv("ROUTES_FILE", "data/raw/routes_clean.json")
VEHICLE_MAP  = os.getenv("VEHICLE_MAP", "data/raw/vehicle_route_mapping.json")
ES_INDEX     = os.getenv("ES_INDEX", "bus_routes")
RECREATE     = os.getenv("RECREATE", "false").lower() == "true"

BUS_ROUTES_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            # ── Identity ─────────────────────────────────────────
            "route_no": {"type": "keyword"},
            # ── Fuzzy-searchable text fields ──────────────────────
            "route_name": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "description": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "operator": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            # Stops are the primary target for stop-name fuzzy search
            "stops_forward": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "stops_return": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            # ── Facet / filter fields ─────────────────────────────
            "route_type":    {"type": "keyword"},
            "fare":          {"type": "keyword"},
            "length":        {"type": "keyword"},
            "schedule":      {"type": "keyword"},
            "frequency":     {"type": "keyword"},
            "trips_per_day": {"type": "keyword"},
            # ── Numeric ───────────────────────────────────────────
            "stop_count_forward": {"type": "integer"},
            "stop_count_return":  {"type": "integer"},
        }
    },
}


# ── Data cleaning ─────────────────────────────────────────────────────────────

def _extract_stops(direction: dict) -> list:
    """Return stops list. Returns [] when data is missing or contains a scraping error."""
    if not direction or "error" in direction:
        return []
    return direction.get("Trạm dừng", {}).get("stops", [])


def _str(value) -> str | None:
    s = str(value).strip() if value is not None else ""
    return s or None


def clean_route(raw: dict) -> dict | None:
    """
    Transform one raw route into a flat ES document keyed by route_no.
    Returns None if the route has no usable identity (no route_no derivable).
    """
    name        = (raw.get("name") or "").strip()
    description = (raw.get("description") or "").strip()
    info        = raw.get("Thông tin") or {}

    stops_forward = _extract_stops(raw.get("luot_di") or {})
    stops_return  = _extract_stops(raw.get("luot_ve") or {})

    # Derive route_no: prefer Thông tin, fall back to parsing the name field
    route_no = _str(info.get("Tuyến số"))
    if not route_no and name.startswith("Tuyến số "):
        route_no = name.removeprefix("Tuyến số ").strip() or None

    if not route_no:
        return None  # cannot identify this route

    route_name = _str(info.get("Tên tuyến")) or description or None

    doc = {
        "route_no":           route_no,
        "route_name":         route_name,
        "description":        description or None,
        "route_type":         _str(info.get("Loại tuyến")),
        "fare":               _str(info.get("Giá vé")),
        "length":             _str(info.get("Độ dài tuyến")),
        "schedule":           _str(info.get("Thời gian chạy")),
        "frequency":          _str(info.get("Giãn cách tuyến")),
        "trips_per_day":      _str(info.get("Số chuyến")),
        "operator":           _str(info.get("Đơn vị")),
        "stops_forward":      stops_forward,
        "stops_return":       stops_return,
        "stop_count_forward": len(stops_forward),
        "stop_count_return":  len(stops_return),
    }

    # Drop None values — ES treats missing fields and null the same for search
    return {k: v for k, v in doc.items() if v is not None}


# ── Index management ──────────────────────────────────────────────────────────

def ensure_index(es: Elasticsearch) -> None:
    exists = es.indices.exists(index=ES_INDEX)
    if exists and RECREATE:
        es.indices.delete(index=ES_INDEX)
        print(f"Dropped existing index '{ES_INDEX}'.")
        exists = False
    if not exists:
        es.indices.create(index=ES_INDEX, **BUS_ROUTES_MAPPING)
        print(f"Created index '{ES_INDEX}'.")
    else:
        print(f"Index '{ES_INDEX}' already exists — skipping creation.")
        print(f"  Set RECREATE=true to drop and rebuild.")


# ── Main ──────────────────────────────────────────────────────────────────────

def load_active_route_nos() -> set:
    """Return normalized route_no set from vehicle_route_mapping.json."""
    if not os.path.exists(VEHICLE_MAP):
        print(f"WARNING: {VEHICLE_MAP} not found — indexing all routes.", file=sys.stderr)
        return set()
    with open(VEHICLE_MAP, encoding="utf-8") as f:
        vmap = json.load(f)
    nos = set()
    for info in vmap.values():
        rno = str(info.get("route_no", "")).strip()
        if rno:
            nos.add(rno.lstrip("0") or "0")
    return nos


def main() -> None:
    print(f"ES host     : {ES_HOST}")
    print(f"Index       : {ES_INDEX}")
    print(f"Routes file : {ROUTES_FILE}")
    print(f"Vehicle map : {VEHICLE_MAP}")

    if not os.path.exists(ROUTES_FILE):
        print(f"ERROR: {ROUTES_FILE} not found.", file=sys.stderr)
        sys.exit(1)

    # Load active route numbers from vehicle_route_mapping.json
    active_nos = load_active_route_nos()
    if active_nos:
        print(f"Active routes in vehicle map: {len(active_nos)}")
    else:
        print("No vehicle map filter applied — indexing all routes.")

    with open(ROUTES_FILE, encoding="utf-8") as f:
        raw_routes = json.load(f)
    print(f"Loaded {len(raw_routes)} raw routes.")

    # Clean, validate, and filter to active routes only
    docs, skipped_invalid, skipped_inactive = [], [], []
    for raw in raw_routes:
        doc = clean_route(raw)
        if not doc:
            skipped_invalid.append(raw.get("name", "<unnamed>"))
            continue
        # Filter: only index routes that have GPS vehicles
        if active_nos and (doc["route_no"].lstrip("0") or "0") not in active_nos:
            skipped_inactive.append(doc["route_no"])
            continue
        docs.append(doc)

    print(f"To index: {len(docs)}  |  No route_no: {len(skipped_invalid)}  |  No GPS vehicles: {len(skipped_inactive)}")
    if skipped_invalid:
        for name in skipped_invalid:
            print(f"  - no route_no: {name}")
    if skipped_inactive:
        print(f"  - no GPS vehicles: {sorted(skipped_inactive)}")

    es = Elasticsearch(ES_HOST)
    ensure_index(es)

    # Use route_no as document _id so re-runs are idempotent
    actions = [
        {"_index": ES_INDEX, "_id": doc["route_no"], "_source": doc}
        for doc in docs
    ]

    success, errors = bulk(es, actions, raise_on_error=False)
    print(f"Indexed: {success}  |  Errors: {len(errors)}")
    if errors:
        for err in errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    print("Done.")


if __name__ == "__main__":
    main()
