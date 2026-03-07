import os

from elasticsearch import Elasticsearch

from ..schemas import NearbySearchResponse
from ..core.route_mapping import get_route_info
from ..core.stop_lookup import get_nearest_stop_name


NEARBY_MAX_RESULTS = int(os.getenv("NEARBY_MAX_RESULTS", "1000"))


def search_nearby_stub(
    lat: float,
    lon: float,
    radius_m: int,
    limit: int | None = None,
    es: Elasticsearch | None = None,
) -> NearbySearchResponse:
    """Search for nearby bus waypoints within a given radius."""
    effective_limit = max(1, min(int(limit or NEARBY_MAX_RESULTS), NEARBY_MAX_RESULTS))

    if es is None:
        return NearbySearchResponse(
            items=[],
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            total=0,
            returned=0,
            limit=effective_limit,
        )

    try:
        # Query Elasticsearch using geo_distance
        query = {
            "query": {
                "bool": {
                    "filter": [
                        {
                            "geo_distance": {
                                "distance": f"{radius_m}m",
                                "location": {
                                    "lat": lat,
                                    "lon": lon
                                }
                            }
                        }
                    ]
                }
            },
            "sort": [
                {
                    "datetime": {
                        "order": "desc",
                        "unmapped_type": "date",
                    }
                },
                {
                    "_geo_distance": {
                        "location": {"lat": lat, "lon": lon},
                        "order": "asc",
                        "unit": "m",
                    }
                }
            ],
            "collapse": {"field": "vehicle"},
            "aggs": {
                "unique_vehicles": {
                    "cardinality": {"field": "vehicle"}
                }
            },
            "size": effective_limit,
            "_source": ["vehicle", "datetime", "location", "speed", "ignition", "aircon"]
        }

        response = es.search(index="bus_waypoints", **query)

        # Format results with route info
        items = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit["_source"]
            loc = source.get("location", {})
            vehicle_id = source.get("vehicle", "")

            # Enrich with route info
            route_info = get_route_info(vehicle_id)

            item = {
                "vehicle": vehicle_id,
                "datetime": source.get("datetime"),
                "x": loc.get("lon", 0),  # longitude
                "y": loc.get("lat", 0),  # latitude
                "speed": source.get("speed"),
                "ignition": source.get("ignition"),
                "aircon": source.get("aircon"),
            }

            if route_info:
                mapping_route_id = route_info.get("route_id")
                mapping_route_no = route_info.get("route_no")
                route_name = route_info.get("route_name")
                item["mapping_route_id"] = mapping_route_id
                item["mapping_route_no"] = mapping_route_no
                if route_name:
                    item["route_name"] = route_name
                elif mapping_route_no:
                    item["route_name"] = f"Tuyen {mapping_route_no}"

            stop_name = get_nearest_stop_name(item["y"], item["x"])
            if stop_name:
                item["stop_name"] = stop_name

            items.append(item)

        unique_vehicles = response.get("aggregations", {}).get("unique_vehicles", {}).get("value")
        total_hits = int(unique_vehicles if unique_vehicles is not None else len(items))

        return NearbySearchResponse(
            items=items,
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            total=total_hits,
            returned=len(items),
            limit=effective_limit,
        )
    except Exception as e:
        print(f"Search error: {e}")
        return NearbySearchResponse(
            items=[],
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            total=0,
            returned=0,
            limit=effective_limit,
        )

