import os

from dotenv import load_dotenv
from elasticsearch import Elasticsearch


# Elasticsearch index mapping for bus GPS waypoints
BUS_WAYPOINT_MAPPING = {
    "mappings": {
        "properties": {
            "vehicle": {"type": "keyword"},
            "datetime": {
                "type": "date",
                "format": "yyyy-MM-dd HH:mm:ss||epoch_millis||strict_date_optional_time"
            },
            "x": {"type": "float"},  # longitude
            "y": {"type": "float"},  # latitude
            "location": {"type": "geo_point"},
            "speed": {"type": "float"},
            "ignition": {"type": "boolean"},
            "aircon": {"type": "boolean"},
            "working": {"type": "boolean"},
            "driver": {"type": "keyword"},
            "route_id": {"type": "keyword"},
            "route_no": {"type": "keyword"},
            "route_name": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "stop_name": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
        }
    }
}


def main() -> None:
    load_dotenv()
    es_host = os.getenv("ES_HOST", "http://localhost:9200")
    es_index = os.getenv("ES_INDEX", "bus_waypoints")

    es = Elasticsearch(es_host)

    if es.indices.exists(index=es_index):
        print(f"Index '{es_index}' đã tồn tại, bỏ qua tạo mới.")
        return

    es.indices.create(index=es_index, **BUS_WAYPOINT_MAPPING)
    print(f"✓ Đã tạo index '{es_index}' với mapping bus_waypoints.")


if __name__ == "__main__":
    main()

