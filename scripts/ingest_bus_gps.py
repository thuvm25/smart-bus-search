"""
Bulk ingest historical GPS data directly into Elasticsearch.

Use this for initial data loading (bypass Kafka pipeline).
For real-time simulation, use the simulator → Kafka → Logstash → ES flow.

Usage:
  python scripts/ingest_bus_gps.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch, helpers
import pandas as pd


PROCESSED_PATH = Path("data/processed/bus_gps_clean.csv")


def main() -> None:
    load_dotenv()
    es_host = os.getenv("ES_HOST", "http://localhost:9200")
    es_index = os.getenv("ES_INDEX", "bus_waypoints")

    if not PROCESSED_PATH.exists():
        raise FileNotFoundError(
            f"CSV not found at {PROCESSED_PATH}. "
            "Run scripts/preprocess.py first."
        )

    df = pd.read_csv(PROCESSED_PATH)
    if not {"x", "y"}.issubset(df.columns):
        raise ValueError("CSV needs columns 'x' (lon) and 'y' (lat).")

    es = Elasticsearch(
        es_host,
        request_timeout=30,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )

    def _iter_docs():
        for row in df.itertuples(index=False):
            doc = row._asdict()
            lon = doc.pop("x")
            lat = doc.pop("y")
            doc["location"] = {"lon": float(lon), "lat": float(lat)}
            doc["lat"] = float(lat)
            doc["lon"] = float(lon)

            cleaned_doc = {}
            for key, val in doc.items():
                if val is None:
                    continue
                try:
                    if pd.isna(val):
                        continue
                except (TypeError, ValueError):
                    pass
                cleaned_doc[key] = val

            yield {"_index": es_index, "_source": cleaned_doc}

    success_count = 0
    error_count = 0
    for ok, action in helpers.streaming_bulk(
        es, _iter_docs(), chunk_size=500, raise_on_error=False
    ):
        if ok:
            success_count += 1
        else:
            error_count += 1
            if error_count <= 3:
                print(f"Error: {action}")

    print(f"Ingest complete: {success_count:,} success, {error_count:,} errors")


if __name__ == "__main__":
    main()
