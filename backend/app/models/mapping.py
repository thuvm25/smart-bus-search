BUS_WAYPOINT_MAPPING = {
    "mappings": {
        "properties": {
            "vehicle": {"type": "keyword"},
            "datetime": {"type": "date"},
            "location": {"type": "geo_point"},
            "ignition": {"type": "boolean"},
            "heading": {"type": "float"},
            "aircon": {"type": "boolean"},
            "door_up": {"type": "boolean"},
            "door_down": {"type": "boolean"},
            "route_name": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword"}},
            },
            "stop_name": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword"}},
            },
        }
    }
}

from elasticsearch import Elasticsearch

from ..config import settings


def get_bus_waypoints_mapping() -> dict:
    """Return the Elasticsearch index mapping for bus waypoints."""
    return {
        "mappings": {
            "properties": {
                "vehicle": {"type": "keyword"},
                "position": {"type": "geo_point"},
                "datetime": {"type": "date"},
                "ignition": {"type": "boolean"},
                "heading": {"type": "integer"},
                "aircon": {"type": "boolean"},
                "door_up": {"type": "boolean"},
                "door_down": {"type": "boolean"},
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


def create_bus_waypoints_index(es: Elasticsearch) -> None:
    """Create the bus_waypoints index if it does not exist."""
    index_name = settings.es_index_bus_waypoints
    if es.indices.exists(index=index_name):
        return

    body = get_bus_waypoints_mapping()
    es.indices.create(index=index_name, **body)

