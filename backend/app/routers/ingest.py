from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from elasticsearch import Elasticsearch
import unicodedata

from ..dependencies import get_es_client, get_index_name
from ..core.route_mapping import get_route_info
from ..core.stop_lookup import get_nearest_stop_name

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
    route_name: str | None = None
    stop_name: str | None = None
    route_name_folded: str | None = None
    stop_name_folded: str | None = None


class BatchIn(BaseModel):
    waypoints: list[WaypointIn]

def _fold_text(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return " ".join(s.split())


@router.post("/waypoint")
async def ingest_one(
    wp: WaypointIn,
    es: Elasticsearch = Depends(get_es_client),
    index: str = Depends(get_index_name),
) -> dict:
    doc = wp.model_dump(exclude_none=True)
    lat = doc.pop("lat")
    lon = doc.pop("lon")
    doc["location"] = {"lat": lat, "lon": lon}

    # Enrich route fields from vehicle mapping if missing.
    if "vehicle" in doc and (doc.get("route_id") is None or doc.get("route_no") is None or doc.get("route_name") is None):
        info = get_route_info(str(doc["vehicle"]))
        if info:
            doc.setdefault("route_id", str(info.get("route_id")) if info.get("route_id") is not None else None)
            doc.setdefault("route_no", info.get("route_no"))
            doc.setdefault("route_name", info.get("route_name"))

    # Enrich nearest stop name if missing.
    if doc.get("stop_name") is None:
        stop = get_nearest_stop_name(float(lat), float(lon))
        if stop:
            doc["stop_name"] = stop

    # Fill folded fields when names exist.
    if doc.get("route_name") and doc.get("route_name_folded") is None:
        doc["route_name_folded"] = _fold_text(str(doc["route_name"]))
    if doc.get("stop_name") and doc.get("stop_name_folded") is None:
        doc["stop_name_folded"] = _fold_text(str(doc["stop_name"]))

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
        lat = doc.pop("lat")
        lon = doc.pop("lon")
        doc["location"] = {"lat": lat, "lon": lon}

        if "vehicle" in doc and (doc.get("route_id") is None or doc.get("route_no") is None or doc.get("route_name") is None):
            info = get_route_info(str(doc["vehicle"]))
            if info:
                doc.setdefault("route_id", str(info.get("route_id")) if info.get("route_id") is not None else None)
                doc.setdefault("route_no", info.get("route_no"))
                doc.setdefault("route_name", info.get("route_name"))

        if doc.get("stop_name") is None:
            stop = get_nearest_stop_name(float(lat), float(lon))
            if stop:
                doc["stop_name"] = stop

        if doc.get("route_name") and doc.get("route_name_folded") is None:
            doc["route_name_folded"] = _fold_text(str(doc["route_name"]))
        if doc.get("stop_name") and doc.get("stop_name_folded") is None:
            doc["stop_name_folded"] = _fold_text(str(doc["stop_name"]))

        actions.append({"index": {"_index": index}})
        actions.append(doc)

    # Make freshly ingested batches immediately searchable for the UI.
    # Trade-off: slightly lower throughput vs refresh=false.
    es.bulk(operations=actions, refresh="wait_for")
    took_ms = round((time.perf_counter() - t0) * 1000, 1)
    return {"status": "ok", "indexed": len(batch.waypoints), "took_ms": took_ms}
