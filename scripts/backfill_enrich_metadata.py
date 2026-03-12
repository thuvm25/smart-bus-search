"""Backfill route/stop metadata into Elasticsearch documents.

This script is meant to be run manually (slow-but-safe) to enrich already-indexed
documents with:
  - route_id / route_no / route_name from vehicle mapping (O(1) lookup)
  - stop_name from nearest stop (haversine, with a max distance threshold)
  - folded fields stop_name_folded / route_name_folded for no-accent search

Typical usage:
  python scripts/backfill_enrich_metadata.py --es-host http://localhost:9200 --index bus_waypoints --only-missing --max-docs 200000
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import unicodedata
from pathlib import Path

from elasticsearch import Elasticsearch, helpers


EARTH_R = 6_371_000.0


def _fold_text(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return " ".join(s.split())


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_R * c


def _load_route_mapping(project_root: Path) -> dict[str, dict]:
    path = project_root / "data" / "raw" / "vehicle_route_mapping.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _load_bus_routes(project_root: Path) -> dict[int, dict]:
    path = project_root / "bus_routes.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    out: dict[int, dict] = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        try:
            bus_id = int(r.get("bus_id"))
        except Exception:
            continue
        out[bus_id] = {"bus_no": r.get("bus_no"), "route_name": r.get("route_name")}
    return out


def _load_stops(project_root: Path) -> list[dict]:
    path = project_root / "bus_stops.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing bus stops file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    out = []
    for s in rows if isinstance(rows, list) else []:
        if not isinstance(s, dict):
            continue
        if s.get("stop_name") is None:
            continue
        lat = s.get("lat")
        lon = s.get("lng", s.get("lon"))
        if lat is None or lon is None:
            continue
        out.append({"stop_name": str(s["stop_name"]), "lat": float(lat), "lon": float(lon)})
    return out


def _nearest_stop_name(stops: list[dict], lat: float, lon: float, max_dist_m: float) -> str | None:
    best_name = None
    best_d = float("inf")
    for s in stops:
        d = _haversine_m(lat, lon, s["lat"], s["lon"])
        if d < best_d:
            best_d = d
            best_name = s["stop_name"]
    if best_name is not None and best_d <= max_dist_m:
        return best_name
    return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill route/stop metadata into ES docs")
    p.add_argument("--es-host", default=os.getenv("ES_HOST", "http://localhost:9200"))
    p.add_argument("--index", default=os.getenv("ES_INDEX", "bus_waypoints"))
    p.add_argument("--only-missing", action="store_true", help="Only update docs missing stop/route fields")
    p.add_argument("--max-docs", type=int, default=None, help="Stop after N docs (for incremental runs)")
    p.add_argument("--batch-size", type=int, default=500)
    p.add_argument("--max-stop-distance-m", type=float, default=800.0)
    p.add_argument("--sleep-ms", type=int, default=0, help="Optional sleep between bulk updates")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parent.parent

    es = Elasticsearch(args.es_host)
    es.info()

    # Ensure folded fields exist in index mapping (safe to call multiple times).
    try:
        es.indices.put_mapping(
            index=args.index,
            properties={
                "stop_name_folded": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
                "route_name_folded": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}},
            },
        )
    except Exception as e:
        print(f"Warning: could not put_mapping for folded fields: {e}")

    route_map = _load_route_mapping(project_root)
    bus_routes = _load_bus_routes(project_root)
    stops = _load_stops(project_root)

    # Query to scan documents.
    if args.only_missing:
        query = {
            "bool": {
                "should": [
                    {"bool": {"must_not": {"exists": {"field": "stop_name"}}}},
                    {"bool": {"must_not": {"exists": {"field": "route_name"}}}},
                    {"bool": {"must_not": {"exists": {"field": "stop_name_folded"}}}},
                    {"bool": {"must_not": {"exists": {"field": "route_name_folded"}}}},
                ],
                "minimum_should_match": 1,
            }
        }
    else:
        query = {"match_all": {}}

    scan_it = helpers.scan(
        es,
        index=args.index,
        query={"query": query, "_source": ["vehicle", "location", "stop_name", "route_id", "route_no", "route_name", "stop_name_folded", "route_name_folded"]},
        size=args.batch_size,
        preserve_order=False,
    )

    pending_updates = []
    processed = 0
    updated = 0
    t0 = time.perf_counter()

    for hit in scan_it:
        processed += 1
        if args.max_docs is not None and processed > args.max_docs:
            break

        src = hit.get("_source") or {}
        vehicle = src.get("vehicle")
        loc = (src.get("location") or {})
        lat = loc.get("lat")
        lon = loc.get("lon")

        doc: dict = {}

        # Route mapping (cheap)
        if vehicle and (src.get("route_id") is None or src.get("route_no") is None or src.get("route_name") is None):
            base = route_map.get(str(vehicle))
            if isinstance(base, dict):
                rid = base.get("route_id")
                rno = base.get("route_no")
                rname = None
                try:
                    rid_int = int(rid) if rid is not None else None
                except Exception:
                    rid_int = None
                if rid_int is not None:
                    meta = bus_routes.get(rid_int)
                    if isinstance(meta, dict):
                        rname = meta.get("route_name")
                if src.get("route_id") is None and rid is not None:
                    doc["route_id"] = str(rid)
                if src.get("route_no") is None and rno is not None:
                    doc["route_no"] = rno
                if src.get("route_name") is None and rname is not None:
                    doc["route_name"] = rname

        # Stop name (expensive)
        if src.get("stop_name") is None and lat is not None and lon is not None:
            try:
                stop = _nearest_stop_name(stops, float(lat), float(lon), args.max_stop_distance_m)
            except Exception:
                stop = None
            if stop:
                doc["stop_name"] = stop

        # Folded fields
        route_name = doc.get("route_name") or src.get("route_name")
        stop_name = doc.get("stop_name") or src.get("stop_name")
        if route_name and (src.get("route_name_folded") is None):
            doc["route_name_folded"] = _fold_text(str(route_name))
        if stop_name and (src.get("stop_name_folded") is None):
            doc["stop_name_folded"] = _fold_text(str(stop_name))

        if not doc:
            continue

        pending_updates.append(
            {
                "_op_type": "update",
                "_index": args.index,
                "_id": hit["_id"],
                "doc": doc,
            }
        )

        if len(pending_updates) >= args.batch_size:
            helpers.bulk(es, pending_updates, refresh=False, raise_on_error=False)
            updated += len(pending_updates)
            pending_updates = []
            if args.sleep_ms > 0:
                time.sleep(args.sleep_ms / 1000.0)

            if processed % (args.batch_size * 10) == 0:
                elapsed = time.perf_counter() - t0
                print(f"processed={processed:,} updated={updated:,} rate={processed/max(elapsed,1e-9):,.0f} docs/s")

    if pending_updates:
        helpers.bulk(es, pending_updates, refresh=False, raise_on_error=False)
        updated += len(pending_updates)

    elapsed = time.perf_counter() - t0
    print("=" * 60)
    print(f"DONE processed={processed:,} updated={updated:,} elapsed={elapsed:.1f}s")
    print("Tip: run again with --only-missing for incremental backfill.")


if __name__ == "__main__":
    main()

