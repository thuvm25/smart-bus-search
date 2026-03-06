from fastapi import APIRouter, Depends
from elasticsearch import Elasticsearch

from ..dependencies import get_es_client
from ..services.analytics_service import analytics_summary_stub


router = APIRouter()


@router.get("/summary")
async def analytics_summary(es: Elasticsearch = Depends(get_es_client)) -> dict:
    return analytics_summary_stub(es=es)

