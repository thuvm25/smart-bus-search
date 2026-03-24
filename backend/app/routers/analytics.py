from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from elasticsearch import Elasticsearch

from ..dependencies import get_es_client, get_index_name
from ..services.analytics_service import (
    active_vehicles_count,
    geo_grid_density,
    index_stats,
    route_stats,
    speed_statistics,
    timeline,
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


@router.get("/timeline")
async def timeline_endpoint(
    minutes: int = Query(60, ge=1),
    interval: str = Query("5m", description="Bucket size, e.g. '5m', '15m', '1h'"),
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    """Time-bucketed vehicle activity over the last N minutes."""
    return timeline(es, index, minutes=minutes, interval=interval)


@router.get("/route-stats")
async def route_stats_endpoint(
    minutes: int | None = Query(None, ge=1),
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    """Per-route statistics: vehicle count, avg speed, record count."""
    return route_stats(es, index, minutes=minutes)


@router.get("/stats")
async def stats(
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    """Basic index-level statistics."""
    return index_stats(es, index)
