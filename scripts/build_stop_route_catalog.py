"""Build unified stop-route catalog from three JSON datasets.

Inputs:
- bus_stops.json
- bus_routes.json
- data/raw/stop_routes_mapping.json

Output records include:
stop_id, stop_name, lat, lng, bus_id, bus_no, route_name
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build merged stop-route catalog")
    parser.add_argument("--stops", type=Path, default=Path("bus_stops.json"))
    parser.add_argument("--routes", type=Path, default=Path("bus_routes.json"))
    parser.add_argument("--mapping", type=Path, default=Path("stop_routes_mapping.json"))
    parser.add_argument("--out-json", type=Path, default=Path("data/processed/stop_route_catalog.json"))
    parser.add_argument("--out-csv", type=Path, default=Path("data/processed/stop_route_catalog.csv"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    stops = _load_json(args.stops)
    routes = _load_json(args.routes)
    mapping_path = args.mapping
    if not mapping_path.exists():
        fallback = Path("data/raw/stop_routes_mapping.json")
        if fallback.exists():
            mapping_path = fallback
    mapping = _load_json(mapping_path)

    stop_by_id = {}
    for s in stops:
        stop_id = s.get("stop_id")
        if stop_id is None:
            continue
        stop_by_id[int(stop_id)] = {
            "stop_id": int(stop_id),
            "stop_name": s.get("stop_name"),
            "lat": s.get("lat"),
            "lng": s.get("lng", s.get("lon")),
        }

    route_by_bus_id = {}
    for r in routes:
        bus_id = r.get("bus_id")
        if bus_id is None:
            continue
        route_by_bus_id[int(bus_id)] = {
            "bus_id": int(bus_id),
            "bus_no": r.get("bus_no"),
            "route_name": r.get("route_name"),
        }

    merged = []
    missing_stop = 0
    missing_route = 0

    for m in mapping:
        stop_id = m.get("stop_id")
        bus_id = m.get("bus_id")
        if stop_id is None or bus_id is None:
            continue

        stop_key = int(stop_id)
        route_key = int(bus_id)

        stop_info = stop_by_id.get(stop_key)
        route_info = route_by_bus_id.get(route_key)

        if stop_info is None:
            missing_stop += 1
            continue

        if route_info is None:
            missing_route += 1

        row = {
            "stop_id": stop_info.get("stop_id"),
            "stop_name": stop_info.get("stop_name"),
            "lat": stop_info.get("lat"),
            "lng": stop_info.get("lng"),
            "bus_id": route_key,
            "bus_no": route_info.get("bus_no") if route_info else None,
            "route_name": route_info.get("route_name") if route_info else None,
        }
        merged.append(row)

    args.out_json.parent.mkdir(parents=True, exist_ok=True)

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["stop_id", "stop_name", "lat", "lng", "bus_id", "bus_no", "route_name"],
        )
        writer.writeheader()
        writer.writerows(merged)

    print(f"Merged rows: {len(merged):,}")
    print(f"Missing stop refs: {missing_stop:,}")
    print(f"Missing route refs: {missing_route:,}")
    print(f"Saved JSON: {args.out_json}")
    print(f"Saved CSV:  {args.out_csv}")


if __name__ == "__main__":
    main()
