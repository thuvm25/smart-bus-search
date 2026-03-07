"""Enrich raw bus GPS records with route information from nearest bus stop.

Logic per GPS record:
1) Compute distance to all stops.
2) Pick nearest stop.
3) If nearest distance <= threshold, assign route_id/route_name from that stop.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

try:
    import numpy as np  # type: ignore

    HAS_NUMPY = True
except Exception:
    np = None  # type: ignore
    HAS_NUMPY = False

EARTH_RADIUS_M = 6_371_000.0


def _load_gps(gps_path: Path) -> pd.DataFrame:
    """Load GPS records from CSV or JSON.

    JSON format supported:
    - list of {"msgBusWayPoint": {...}}
    - list of waypoint dicts containing x/y directly
    """
    suffix = gps_path.suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(gps_path)

    if suffix == ".json":
        with open(gps_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        if not isinstance(raw, list):
            raise ValueError("JSON GPS input must be a list.")

        rows: list[dict] = []
        for item in raw:
            if isinstance(item, dict) and "msgBusWayPoint" in item:
                waypoint = item.get("msgBusWayPoint")
                if isinstance(waypoint, dict):
                    rows.append(waypoint)
            elif isinstance(item, dict):
                rows.append(item)

        return pd.DataFrame(rows)

    raise ValueError(f"Unsupported GPS file type: {gps_path}")


def _load_stops(stops_path: Path) -> pd.DataFrame:
    with open(stops_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    stops_df = pd.DataFrame(raw)

    # Normalize column names across possible schemas.
    lon_col = "lon" if "lon" in stops_df.columns else "lng" if "lng" in stops_df.columns else None
    lat_col = "lat" if "lat" in stops_df.columns else None

    if lat_col is None or lon_col is None:
        raise ValueError("Bus stop dataset must contain lat and lon/lng columns.")

    rename_map = {lat_col: "lat", lon_col: "lon"}
    stops_df = stops_df.rename(columns=rename_map)

    required = ["stop_id", "stop_name", "lat", "lon"]
    for col in required:
        if col not in stops_df.columns:
            raise ValueError(f"Bus stop dataset is missing required column: {col}")

    # route_id/route_name may be missing in some stop datasets.
    if "route_id" not in stops_df.columns:
        stops_df["route_id"] = None
    if "route_name" not in stops_df.columns:
        stops_df["route_name"] = None

    stops_df = stops_df[["stop_id", "stop_name", "route_id", "route_name", "lat", "lon"]].copy()
    stops_df["lat"] = pd.to_numeric(stops_df["lat"], errors="coerce")
    stops_df["lon"] = pd.to_numeric(stops_df["lon"], errors="coerce")
    stops_df = stops_df.dropna(subset=["lat", "lon"]).reset_index(drop=True)

    return stops_df


def _merge_stop_route_from_excel(stops_df: pd.DataFrame, xlsx_path: Path) -> pd.DataFrame:
    """Populate route fields using Excel sheets: stop_routes_mapping + bus_routes.

    Expected sheets:
    - stop_routes_mapping(stop_id, bus_id)
    - bus_routes(bus_id, bus_no, route_name)
    """
    if not xlsx_path.exists():
        print(f"Excel mapping not found: {xlsx_path} (skip)")
        return stops_df

    try:
        map_df = pd.read_excel(xlsx_path, sheet_name="stop_routes_mapping")
        routes_df = pd.read_excel(xlsx_path, sheet_name="bus_routes")
    except Exception as e:
        print(f"Cannot read mapping sheets from {xlsx_path}: {e} (skip)")
        return stops_df

    required_map = {"stop_id", "bus_id"}
    required_routes = {"bus_id", "route_name"}
    if not required_map.issubset(set(map_df.columns)):
        print("Sheet 'stop_routes_mapping' missing required columns stop_id,bus_id (skip)")
        return stops_df
    if not required_routes.issubset(set(routes_df.columns)):
        print("Sheet 'bus_routes' missing required columns bus_id,route_name (skip)")
        return stops_df

    map_df = map_df[["stop_id", "bus_id"]].copy()
    routes_df = routes_df[["bus_id", "route_name"]].copy()

    map_df["stop_id"] = pd.to_numeric(map_df["stop_id"], errors="coerce").astype("Int64")
    map_df["bus_id"] = pd.to_numeric(map_df["bus_id"], errors="coerce").astype("Int64")
    routes_df["bus_id"] = pd.to_numeric(routes_df["bus_id"], errors="coerce").astype("Int64")

    merged = map_df.merge(routes_df, on="bus_id", how="left")
    merged = merged.dropna(subset=["stop_id", "bus_id", "route_name"]).copy()

    # One stop may map to multiple routes; pick the smallest bus_id deterministically.
    merged = merged.sort_values(["stop_id", "bus_id"]).drop_duplicates(subset=["stop_id"], keep="first")
    merged = merged.rename(columns={"bus_id": "route_id"})

    out = stops_df.copy()
    out["stop_id"] = pd.to_numeric(out["stop_id"], errors="coerce").astype("Int64")
    out = out.merge(merged[["stop_id", "route_id", "route_name"]], on="stop_id", how="left", suffixes=("", "_xlsx"))

    # Prefer explicit stop fields; fill missing values from xlsx mapping.
    if "route_id_xlsx" in out.columns:
        out["route_id"] = out["route_id"].where(out["route_id"].notna(), out["route_id_xlsx"])
    if "route_name_xlsx" in out.columns:
        out["route_name"] = out["route_name"].where(out["route_name"].notna(), out["route_name_xlsx"])

    out = out.drop(columns=[c for c in ["route_id_xlsx", "route_name_xlsx"] if c in out.columns])
    filled = out["route_name"].notna().sum()
    print(f"Filled route metadata from Excel mapping: {filled:,}/{len(out):,} stops")
    return out


def _haversine_min_distance_indices(
    gps_lat,
    gps_lon,
    stops_lat,
    stops_lon,
):
    """Return nearest stop index and distance (meters) for each GPS point."""
    gps_lat_rad = np.radians(gps_lat)[:, None]
    gps_lon_rad = np.radians(gps_lon)[:, None]
    stops_lat_rad = np.radians(stops_lat)[None, :]
    stops_lon_rad = np.radians(stops_lon)[None, :]

    dlat = stops_lat_rad - gps_lat_rad
    dlon = stops_lon_rad - gps_lon_rad

    a = np.sin(dlat / 2.0) ** 2 + np.cos(gps_lat_rad) * np.cos(stops_lat_rad) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    distances = EARTH_RADIUS_M * c

    nearest_idx = np.argmin(distances, axis=1)
    nearest_dist = distances[np.arange(distances.shape[0]), nearest_idx]
    return nearest_idx, nearest_dist


def _haversine_point_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between 2 coordinates in meters (fallback path without numpy)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def _resolve_gps_columns(gps_df: pd.DataFrame, lat_col: str, lon_col: str) -> tuple[str, str]:
    """Resolve coordinate columns with automatic fallback names."""
    if lat_col in gps_df.columns and lon_col in gps_df.columns:
        return lat_col, lon_col

    candidates = [
        ("y", "x"),
        ("lat", "lon"),
        ("latitude", "longitude"),
        ("lat", "lng"),
    ]
    for cand_lat, cand_lon in candidates:
        if cand_lat in gps_df.columns and cand_lon in gps_df.columns:
            return cand_lat, cand_lon

    cols = ", ".join(gps_df.columns.astype(str).tolist())
    raise ValueError(
        f"Khong tim thay cot toa do hop le. Requested: ({lat_col}, {lon_col}). "
        f"Available: [{cols}]"
    )


def enrich_gps_with_routes(
    gps_df: pd.DataFrame,
    stops_df: pd.DataFrame,
    gps_lat_col: str,
    gps_lon_col: str,
    threshold_m: float,
    chunk_size: int,
    include_route_name: bool = False,
) -> pd.DataFrame:
    """Enrich GPS records with nearest stop + route fields."""
    gps_lat_col, gps_lon_col = _resolve_gps_columns(gps_df, gps_lat_col, gps_lon_col)

    gps_df = gps_df.copy()
    gps_df[gps_lat_col] = pd.to_numeric(gps_df[gps_lat_col], errors="coerce")
    gps_df[gps_lon_col] = pd.to_numeric(gps_df[gps_lon_col], errors="coerce")

    n = len(gps_df)

    if HAS_NUMPY:
        out_stop_id = np.full(n, np.nan, dtype=float)
        out_stop_name = np.full(n, None, dtype=object)
        out_route_id = np.full(n, np.nan, dtype=float)
        out_route_name = np.full(n, None, dtype=object) if include_route_name else None
        out_distance = np.full(n, np.nan, dtype=float)
        stops_lat = stops_df["lat"].to_numpy(dtype=float)
        stops_lon = stops_df["lon"].to_numpy(dtype=float)
    else:
        out_stop_id = [None] * n
        out_stop_name = [None] * n
        out_route_id = [None] * n
        out_route_name = [None] * n if include_route_name else None
        out_distance = [None] * n
        stop_tuples = list(
            zip(
                stops_df["stop_id"].tolist(),
                stops_df["stop_name"].tolist(),
                stops_df["route_id"].tolist(),
                stops_df["route_name"].tolist(),
                stops_df["lat"].astype(float).tolist(),
                stops_df["lon"].astype(float).tolist(),
            )
        )

    for start in range(0, n, chunk_size):
        end = min(start + chunk_size, n)
        chunk = gps_df.iloc[start:end]

        valid_mask = chunk[gps_lat_col].notna() & chunk[gps_lon_col].notna()
        if not valid_mask.any():
            continue

        if HAS_NUMPY:
            valid_idx_local = np.where(valid_mask.to_numpy())[0]
            valid_idx_global = start + valid_idx_local

            lat_vals = chunk.loc[valid_mask, gps_lat_col].to_numpy(dtype=float)
            lon_vals = chunk.loc[valid_mask, gps_lon_col].to_numpy(dtype=float)

            nearest_idx, nearest_dist = _haversine_min_distance_indices(lat_vals, lon_vals, stops_lat, stops_lon)
            within = nearest_dist <= threshold_m

            if within.any():
                matched_global = valid_idx_global[within]
                matched_stop_idx = nearest_idx[within]

                matched_stops = stops_df.iloc[matched_stop_idx]

                out_stop_id[matched_global] = matched_stops["stop_id"].to_numpy(dtype=float)
                out_stop_name[matched_global] = matched_stops["stop_name"].astype(str).to_numpy()
                out_distance[matched_global] = nearest_dist[within]

                # route_id/route_name can be missing in stop dataset.
                out_route_id[matched_global] = pd.to_numeric(
                    matched_stops["route_id"], errors="coerce"
                ).to_numpy(dtype=float)
                if include_route_name and out_route_name is not None:
                    route_names = matched_stops["route_name"].where(
                        matched_stops["route_name"].notna(), None
                    )
                    out_route_name[matched_global] = route_names.to_numpy(dtype=object)
        else:
            for row_idx, row in chunk.loc[valid_mask].iterrows():
                lat = float(row[gps_lat_col])
                lon = float(row[gps_lon_col])
                best = None
                best_d = float("inf")

                for stop_id, stop_name, route_id, route_name, s_lat, s_lon in stop_tuples:
                    d = _haversine_point_m(lat, lon, s_lat, s_lon)
                    if d < best_d:
                        best_d = d
                        best = (stop_id, stop_name, route_id, route_name)

                if best is not None and best_d <= threshold_m:
                    idx = int(row_idx)
                    out_stop_id[idx] = best[0]
                    out_stop_name[idx] = best[1]
                    out_distance[idx] = best_d
                    out_route_id[idx] = best[2]
                    if include_route_name and out_route_name is not None:
                        out_route_name[idx] = best[3]

    gps_df["nearest_stop_id"] = pd.Series(out_stop_id, index=gps_df.index).astype("Int64")
    gps_df["nearest_stop_name"] = pd.Series(out_stop_name, index=gps_df.index)
    gps_df["distance_to_stop_m"] = pd.to_numeric(pd.Series(out_distance, index=gps_df.index), errors="coerce")

    # Requested output fields.
    gps_df["route_id"] = pd.to_numeric(pd.Series(out_route_id, index=gps_df.index), errors="coerce").astype("Int64")
    if include_route_name and out_route_name is not None:
        gps_df["route_name"] = pd.Series(out_route_name, index=gps_df.index)

    return gps_df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich GPS records with route_id from nearest stop")
    parser.add_argument("--gps-path", type=Path, default=Path("data/processed/bus_gps_clean.csv"))
    parser.add_argument("--stops-path", type=Path, default=Path("bus_stops.json"))
    parser.add_argument("--output-path", type=Path, default=Path("data/processed/bus_gps_enriched.csv"))
    parser.add_argument("--gps-lat-col", type=str, default="y", help="GPS latitude column")
    parser.add_argument("--gps-lon-col", type=str, default="x", help="GPS longitude column")
    parser.add_argument("--threshold-m", type=float, default=100.0, help="Nearest stop max distance")
    parser.add_argument("--chunk-size", type=int, default=2000, help="Rows per distance-compute chunk")
    parser.add_argument("--max-rows", type=int, default=None, help="Optional debug limit")
    parser.add_argument(
        "--include-route-name",
        action="store_true",
        help="Also write route_name (increases output size).",
    )
    parser.add_argument(
        "--mapping-xlsx",
        type=Path,
        default=Path("DataBus.xlsx"),
        help="Excel file containing sheets stop_routes_mapping and bus_routes",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if HAS_NUMPY:
        print("Distance engine: numpy (fast)")
    else:
        print("Distance engine: pure python (slow) - numpy not installed")

    print(f"Loading GPS data: {args.gps_path}")
    gps_df = _load_gps(args.gps_path)
    if args.max_rows is not None:
        gps_df = gps_df.head(args.max_rows).copy()
        print(f"Using first {len(gps_df)} rows for debug.")

    print(f"Loading stops data: {args.stops_path}")
    stops_df = _load_stops(args.stops_path)
    stops_df = _merge_stop_route_from_excel(stops_df, args.mapping_xlsx)

    print(f"GPS rows: {len(gps_df):,} | Stops: {len(stops_df):,}")
    print(
        f"Enriching with threshold={args.threshold_m}m, "
        f"chunk_size={args.chunk_size}..."
    )

    enriched_df = enrich_gps_with_routes(
        gps_df=gps_df,
        stops_df=stops_df,
        gps_lat_col=args.gps_lat_col,
        gps_lon_col=args.gps_lon_col,
        threshold_m=args.threshold_m,
        chunk_size=args.chunk_size,
        include_route_name=args.include_route_name,
    )

    matched_stop = enriched_df["nearest_stop_name"].notna().sum()
    print(f"Matched nearest_stop: {matched_stop:,}/{len(enriched_df):,} ({matched_stop / max(len(enriched_df), 1):.2%})")
    matched_route_id = enriched_df["route_id"].notna().sum()
    print(f"Matched route_id: {matched_route_id:,}/{len(enriched_df):,} ({matched_route_id / max(len(enriched_df), 1):.2%})")
    if args.include_route_name and "route_name" in enriched_df.columns:
        matched_route_name = enriched_df["route_name"].notna().sum()
        print(
            f"Matched route_name: {matched_route_name:,}/{len(enriched_df):,} "
            f"({matched_route_name / max(len(enriched_df), 1):.2%})"
        )

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    enriched_df.to_csv(args.output_path, index=False)
    print(f"Saved enriched data to: {args.output_path}")


if __name__ == "__main__":
    main()
