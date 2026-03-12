from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from elasticsearch import Elasticsearch

from ..dependencies import get_es_client, get_index_name
from ..services.analytics_service import (
    active_vehicles_count,
    geo_grid_density,
    index_stats,
    realtime_ingest_metrics,
    speed_statistics,
)

router = APIRouter()


@router.get("/density")
async def density(
    precision: int = Query(5, ge=1, le=12),
    minutes: int | None = Query(None, ge=1),
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    """Geohash grid density of bus waypoints."""
    return geo_grid_density(es, index, precision=precision, minutes=minutes)


@router.get("/active-count")
async def active_count(
    minutes: int = Query(5, ge=1),
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    """Number of distinct vehicles active in the last N minutes."""
    return active_vehicles_count(es, index, minutes=minutes)


@router.get("/speed")
async def speed(
    minutes: int | None = Query(None, ge=1),
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    """Speed statistics across all records."""
    return speed_statistics(es, index, minutes=minutes)


@router.get("/stats")
async def stats(
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    """Basic index-level statistics."""
    return index_stats(es, index)


@router.get("/realtime")
async def realtime(
    window_seconds: int = Query(60, ge=1, le=3600),
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    """Realtime ingest metrics (records/vehicles/latest) for last N seconds."""
    return realtime_ingest_metrics(es, index, window_seconds=window_seconds)
