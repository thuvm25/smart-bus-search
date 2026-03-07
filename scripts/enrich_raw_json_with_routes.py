"""Enrich raw sub_raw JSON records with nearest-stop route metadata.

This keeps the original list structure and updates each `msgBusWayPoint` object,
so downstream scripts that read raw JSON can still work unchanged.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from enrich_gps_with_routes import (  # type: ignore
    _load_stops,
    _merge_stop_route_from_excel,
    enrich_gps_with_routes,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich raw JSON (msgBusWayPoint) with route_id/stop_name"
    )
    parser.add_argument(
        "--input-json",
        type=Path,
        required=True,
        help="Path to sub_raw_*.json",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Output JSON path (default: input stem + _enriched.json)",
    )
    parser.add_argument("--stops-path", type=Path, default=Path("bus_stops.json"))
    parser.add_argument("--mapping-xlsx", type=Path, default=Path("DataBus.xlsx"))
    parser.add_argument("--threshold-m", type=float, default=120.0)
    parser.add_argument("--chunk-size", type=int, default=2000)
    parser.add_argument(
        "--include-route-name",
        action="store_true",
        help="Also write route_name to output JSON (larger output).",
    )
    return parser.parse_args()


def _default_output_path(input_json: Path) -> Path:
    return input_json.with_name(f"{input_json.stem}_enriched.json")


def main() -> None:
    args = parse_args()
    output_path = args.output_json or _default_output_path(args.input_json)

    with open(args.input_json, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        raise ValueError("Input JSON must be a list of records.")

    waypoint_rows: list[dict] = []
    waypoint_indices: list[int] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        wp = item.get("msgBusWayPoint")
        if isinstance(wp, dict):
            waypoint_rows.append(wp)
            waypoint_indices.append(idx)

    if not waypoint_rows:
        raise ValueError("No msgBusWayPoint records found in input JSON.")

    gps_df = pd.DataFrame(waypoint_rows)
    stops_df = _load_stops(args.stops_path)
    stops_df = _merge_stop_route_from_excel(stops_df, args.mapping_xlsx)

    enriched = enrich_gps_with_routes(
        gps_df=gps_df,
        stops_df=stops_df,
        gps_lat_col="y",
        gps_lon_col="x",
        threshold_m=args.threshold_m,
        chunk_size=args.chunk_size,
        include_route_name=args.include_route_name,
    )

    route_id_hits = 0
    route_name_hits = 0
    for row_i, raw_i in enumerate(waypoint_indices):
        wp = raw[raw_i]["msgBusWayPoint"]
        stop_name = enriched.iloc[row_i].get("nearest_stop_name")
        route_id = enriched.iloc[row_i].get("route_id")
        route_name = enriched.iloc[row_i].get("route_name") if args.include_route_name else None

        if pd.notna(stop_name):
            wp["stop_name"] = str(stop_name)
        if pd.notna(route_id):
            wp["route_id"] = int(route_id)
            route_id_hits += 1
        if args.include_route_name and pd.notna(route_name):
            wp["route_name"] = str(route_name)
            route_name_hits += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)

    print(f"Input rows: {len(waypoint_rows):,}")
    print(f"Rows with route_id: {route_id_hits:,}/{len(waypoint_rows):,}")
    if args.include_route_name:
        print(f"Rows with route_name: {route_name_hits:,}/{len(waypoint_rows):,}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
