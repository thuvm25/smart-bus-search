from elasticsearch import Elasticsearch

from ..schemas import NearbySearchResponse


def search_nearby_stub(
    lat: float,
    lon: float,
    radius_m: int,
    es: Elasticsearch | None = None,
) -> NearbySearchResponse:
    # Skeleton implementation – replace with real Elasticsearch query later.
    return NearbySearchResponse(items=[], lat=lat, lon=lon, radius_m=radius_m)

