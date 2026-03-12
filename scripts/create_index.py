"""Create the bus_waypoints index in Elasticsearch with the proper mapping."""

import os
import sys

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.app.models.mapping import BUS_WAYPOINT_MAPPING


def main() -> None:
    load_dotenv()
    es_host = os.getenv("ES_HOST", "http://localhost:9200")
    es_index = os.getenv("ES_INDEX", "bus_waypoints")

    es = Elasticsearch(es_host)

    if es.indices.exists(index=es_index):
        print(f"Index '{es_index}' already exists — skipping.")
        return

    es.indices.create(index=es_index, **BUS_WAYPOINT_MAPPING)
    print(f"Created index '{es_index}'.")


if __name__ == "__main__":
    main()
