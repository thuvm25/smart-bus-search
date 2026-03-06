import os

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

from backend.app.models.mapping import BUS_WAYPOINT_MAPPING


def main() -> None:
    load_dotenv()
    es_host = os.getenv("ES_HOST", "http://localhost:9200")
    es_index = os.getenv("ES_INDEX", "bus_waypoints")

    es = Elasticsearch(es_host)

    if es.indices.exists(index=es_index):
        print(f"Index '{es_index}' đã tồn tại, bỏ qua tạo mới.")
        return

    es.indices.create(index=es_index, **BUS_WAYPOINT_MAPPING)
    print(f"Đã tạo index '{es_index}' với mapping bus_waypoints.")


if __name__ == "__main__":
    main()

