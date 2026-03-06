from fastapi import APIRouter, Depends
from elasticsearch import Elasticsearch

from ..dependencies import get_es_client
from ..schemas import NearbySearchResponse
from ..services.search_service import search_nearby_stub


router = APIRouter()


@router.get("/nearby", response_model=NearbySearchResponse)
async def search_nearby(
    lat: float,
    lon: float,
    radius_m: int = 500,
    es: Elasticsearch = Depends(get_es_client),
) -> NearbySearchResponse:
    return search_nearby_stub(lat=lat, lon=lon, radius_m=radius_m, es=es)

