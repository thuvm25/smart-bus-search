from fastapi import APIRouter, Depends
from pydantic import BaseModel
from elasticsearch import Elasticsearch

from ..dependencies import get_es_client
from ..schemas import NearbySearchResponse
from ..services.search_service import search_nearby_stub
from ..core.route_mapping import get_route_info
from ..core.stop_lookup import get_nearest_stop_name


router = APIRouter()


class NearbySearchRequest(BaseModel):
    center: dict
    radius_m: int = 500
    time_window_minutes: int = 5
    limit: int | None = None


class ActiveSearchRequest(BaseModel):
    time_window_minutes: int = 5


class VehicleTraceRequest(BaseModel):
    vehicle: str
    time_window_minutes: int = 60


@router.get("/nearby", response_model=NearbySearchResponse)
async def search_nearby(
    lat: float,
    lon: float,
    radius_m: int = 500,
    limit: int | None = None,
    es: Elasticsearch = Depends(get_es_client),
) -> NearbySearchResponse:
    return search_nearby_stub(lat=lat, lon=lon, radius_m=radius_m, limit=limit, es=es)


@router.post("/nearby", response_model=NearbySearchResponse)
async def search_nearby_post(
    req: NearbySearchRequest,
    es: Elasticsearch = Depends(get_es_client),
) -> NearbySearchResponse:
    """Search for nearby buses with time window filter."""
    lat = req.center.get("lat", 0)
    lon = req.center.get("lon", 0)
    radius_m = req.radius_m

    # Add time window filtering if needed
    return search_nearby_stub(lat=lat, lon=lon, radius_m=radius_m, limit=req.limit, es=es)


@router.post("/active")
async def search_active(
    req: ActiveSearchRequest,
    es: Elasticsearch = Depends(get_es_client),
) -> dict:
    """Search for active buses in the last N minutes."""
    if es is None:
        return {"items": [], "total": 0}

    try:
        # Return one latest waypoint per vehicle.
        query = {
            "query": {
                "match_all": {}
            },
            "size": 1000,
            "sort": [
                {
                    "datetime": {
                        "order": "desc",
                        "unmapped_type": "date",
                    }
                }
            ],
            "collapse": {"field": "vehicle"},
            "_source": ["vehicle", "datetime", "location", "speed", "ignition"]
        }

        response = es.search(index="bus_waypoints", **query)

        items = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit["_source"]
            vehicle_id = source.get("vehicle")
            loc = source.get("location", {})

            # Enrich with route info
            route_info = get_route_info(vehicle_id)

            vehicle_data = {
                "vehicle": vehicle_id,
                "datetime": source.get("datetime"),
                "lat": loc.get("lat"),
                "lon": loc.get("lon"),
                "speed": source.get("speed"),
                "ignition": source.get("ignition"),
            }

            if route_info:
                mapping_route_id = route_info.get("route_id")
                mapping_route_no = route_info.get("route_no")
                route_name = route_info.get("route_name")
                vehicle_data["mapping_route_id"] = mapping_route_id
                vehicle_data["mapping_route_no"] = mapping_route_no
                if route_name:
                    vehicle_data["route_name"] = route_name
                elif mapping_route_no:
                    vehicle_data["route_name"] = f"Tuyen {mapping_route_no}"

            stop_name = get_nearest_stop_name(vehicle_data["lat"], vehicle_data["lon"])
            if stop_name:
                vehicle_data["stop_name"] = stop_name

            items.append(vehicle_data)

        return {"items": items, "total": len(items)}
    except Exception as e:
        print(f"Search active error: {e}")
        return {"items": [], "total": 0}


@router.post("/vehicle-trace")
async def search_vehicle_trace(
    req: VehicleTraceRequest,
    es: Elasticsearch = Depends(get_es_client),
) -> dict:
    """Get GPS trace for a specific vehicle in the last N minutes."""
    if es is None:
        return {"items": [], "total": 0, "vehicle": req.vehicle}

    try:
        # Query specific vehicle's waypoints
        query = {
            "query": {
                "term": {"vehicle": req.vehicle}
            },
            "size": 1000,
            "sort": [{"datetime": "asc"}],
            "_source": ["vehicle", "datetime", "location", "speed", "ignition"]
        }

        response = es.search(index="bus_waypoints", **query)

        # Enrich with route info
        route_info = get_route_info(req.vehicle)

        items = []
        for hit in response.get("hits", {}).get("hits", []):
            source = hit["_source"]
            loc = source.get("location", {})
            item = {
                "datetime": source.get("datetime"),
                "lat": loc.get("lat"),
                "lon": loc.get("lon"),
                "speed": source.get("speed"),
                "ignition": source.get("ignition"),
            }
            stop_name = get_nearest_stop_name(item["lat"], item["lon"])
            if stop_name:
                item["stop_name"] = stop_name
            items.append(item)

        result = {"items": items, "total": len(items), "vehicle": req.vehicle}
        if route_info:
            mapping_route_id = route_info.get("route_id")
            mapping_route_no = route_info.get("route_no")
            route_name = route_info.get("route_name")
            result["mapping_route_id"] = mapping_route_id
            result["mapping_route_no"] = mapping_route_no
            if route_name:
                result["route_name"] = route_name
            elif mapping_route_no:
                result["route_name"] = f"Tuyen {mapping_route_no}"

        return result
    except Exception as e:
        print(f"Vehicle trace error: {e}")
        return {"items": [], "total": 0, "vehicle": req.vehicle}

