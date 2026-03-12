from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from elasticsearch import Elasticsearch

from ..dependencies import get_es_client, get_index_name

router = APIRouter()


class WaypointIn(BaseModel):
    vehicle: str
    datetime: str
    lat: float
    lon: float
    speed: float | None = None
    ignition: bool | None = None
    heading: float | None = None
    aircon: bool | None = None
    door_up: bool | None = None
    door_down: bool | None = None
    route_id: str | None = None
    route_no: str | None = None


class BatchIn(BaseModel):
    waypoints: list[WaypointIn]


@router.post("/waypoint")
async def ingest_one(
    wp: WaypointIn,
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    doc = wp.model_dump(exclude_none=True)
    doc["location"] = {"lat": doc.pop("lat"), "lon": doc.pop("lon")}
    es.index(index=index, document=doc)
    return {"status": "ok", "indexed": 1}


@router.post("/batch")
async def ingest_batch(
    batch: BatchIn,
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    if not batch.waypoints:
        return {"status": "ok", "indexed": 0, "took_ms": 0}

    t0 = time.perf_counter()
    actions = []
    for wp in batch.waypoints:
        doc = wp.model_dump(exclude_none=True)
        doc["location"] = {"lat": doc.pop("lat"), "lon": doc.pop("lon")}
        actions.append({"index": {"_index": index}})
        actions.append(doc)

    es.bulk(operations=actions, refresh="false")
    took_ms = round((time.perf_counter() - t0) * 1000, 1)
    return {"status": "ok", "indexed": len(batch.waypoints), "took_ms": took_ms}
