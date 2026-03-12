BUS_WAYPOINT_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "vehicle": {"type": "keyword"},
            "datetime": {
                "type": "date",
                "format": "yyyy-MM-dd HH:mm:ss||epoch_millis||strict_date_optional_time",
            },
            "location": {"type": "geo_point"},
            "speed": {"type": "float"},
            "ignition": {"type": "boolean"},
            "heading": {"type": "float"},
            "aircon": {"type": "boolean"},
            "door_up": {"type": "boolean"},
            "door_down": {"type": "boolean"},
            "working": {"type": "boolean"},
            "driver": {"type": "keyword"},
            "route_id": {"type": "keyword"},
            "route_no": {"type": "keyword"},
            "route_name": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            # "Folded" fields store the same content but without diacritics (Vietnamese accents)
            # to support queries like "an suong" matching "An Sương".
            "route_name_folded": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "stop_name": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
            "stop_name_folded": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
            },
        }
    },
}
