"""
Create the bus_waypoints index in Elasticsearch with the proper mapping.

Standalone script — no dependency on backend module.
Usage:
  python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt
  .venv/bin/python scripts/create_index.py
  # or with custom host:
  ES_HOST=http://localhost:9200 .venv/bin/python scripts/create_index.py
"""

import os
import re

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None 

from elasticsearch import Elasticsearch


_VALID_INDEX_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


BUS_WAYPOINT_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            # ── Identity ────────────────────────────────────────
            "vehicle":  {"type": "keyword"},
            "driver":   {"type": "keyword"},
            # ── Time ────────────────────────────────────────────
            "datetime": {
                "type":   "date",
                "format": "strict_date_optional_time||yyyy-MM-dd'T'HH:mm:ss.SSSSSSZ||yyyy-MM-dd HH:mm:ss||epoch_millis",
            },
            # ── Location ─────────────────────────────────────────
            "location": {"type": "geo_point"},
            "lat":      {"type": "float"},
            "lon":      {"type": "float"},
            # ── Telemetry ────────────────────────────────────────
            "speed":     {"type": "float"},
            "heading":   {"type": "float"},
            "ignition":  {"type": "boolean"},
            "aircon":    {"type": "boolean"},
            "working":   {"type": "boolean"},
            "door_up":   {"type": "boolean"},
            "door_down": {"type": "boolean"},
            # ── Route enrichment ─────────────────────────────────
            "route_id":  {"type": "keyword"},
            "route_no":  {"type": "keyword"},
            "plate_no":  {"type": "keyword"},
            # route_name: human-readable, e.g. "Bến Thành - Suối Tiên"
            #   text  → full-text search
            #   .keyword → exact-match aggregations / Kibana filter-by-value
            "route_name": {
                "type":   "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
        }
    },
}


def _read_index_name() -> str:
    raw_index = os.getenv("ES_INDEX", "bus_waypoints")
    es_index = raw_index.strip()
    if not es_index:
        raise ValueError("ES_INDEX is empty after trimming whitespace.")

    # Fail fast with a clear message if the environment variable was polluted
    # by pasted shell text or invalid characters.
    if not _VALID_INDEX_PATTERN.fullmatch(es_index):
        snippet = raw_index if len(raw_index) <= 120 else f"{raw_index[:117]}..."
        raise ValueError(
            "Invalid ES_INDEX value. Use only lowercase letters, digits, dots, "
            f"underscores, and dashes. Current value: {snippet!r}"
        )
    return es_index


def main() -> None:
    if load_dotenv is not None:
        load_dotenv()
    es_host = os.getenv("ES_HOST", "http://localhost:9200")
    es_index = _read_index_name()
    print(f"Using Elasticsearch host: {es_host}")
    print(f"Using index name: {es_index}")

    es = Elasticsearch(es_host)

    if es.indices.exists(index=es_index):
        print(f"Index '{es_index}' already exists — skipping creation.")
        print(f"  To recreate: curl -X DELETE {es_host}/{es_index}")
        return

    es.indices.create(index=es_index, **BUS_WAYPOINT_MAPPING)
    print(f"Created index '{es_index}' with geo_point mapping.")


if __name__ == "__main__":
    main()
