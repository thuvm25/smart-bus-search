"""
GPS Simulator — streams bus GPS records to Kafka, simulating real-time IoT devices.

Two modes (DATA_MODE env var):
  json  [default] — reads raw JSON files from data/ (flat)
  csv             — reads the pre-processed CSV (legacy / quick dev mode)

JSON mode flow:
  1. Glob all sub_raw_*.json files from JSON_DIR/data/
  2. Load enrichment table: vehicle hash → {route_id, route_no, route_name}
  3. Stream file-by-file: extract msgBusWayPoint, sort by datetime within each file,
     shift timestamps so the first record maps to "now", send to Kafka in batches.

CSV mode flow:
  1. Load bus_gps_clean.csv, sort by datetime, shift timestamps, stream in batches.

Environment variables:
  DATA_MODE               – "json" or "csv" (default: json)
  JSON_DIR                – directory containing data/ (default: /app/data/raw)
  VEHICLE_MAP             – path to vehicle_route_mapping.json
  ROUTES_FILE             – path to routes_clean.json
  MAX_FILES               – max JSON files to process, 0 = all (default: 0)
  KAFKA_BOOTSTRAP_SERVERS – e.g. kafka:9092
  KAFKA_TOPIC             – Kafka topic name (default: bus-gps-raw)
  CSV_PATH                – path to processed CSV (csv mode only)
  BATCH_SIZE              – records per batch (default: 50)
  DELAY_MS                – milliseconds between batches (default: 200)
  SPEED_MULTIPLIER        – playback speed factor, higher = faster (default: 1.0)
  LOOP                    – "true" to restart when data is exhausted
"""

from __future__ import annotations

import glob
import json
import os
import re
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Generator

import pandas as pd
from dotenv import find_dotenv, load_dotenv
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

load_dotenv(find_dotenv())

# ── Configuration ────────────────────────────────────────────────────────────
DATA_MODE   = os.getenv("DATA_MODE", "json").lower()
JSON_DIR    = os.getenv("JSON_DIR", "/app/data/raw")
VEHICLE_MAP = os.getenv("VEHICLE_MAP", "/app/data/raw/vehicle_route_mapping.json")
ROUTES_FILE = os.getenv("ROUTES_FILE", "/app/data/raw/routes_clean.json")
MAX_FILES   = int(os.getenv("MAX_FILES", "0"))

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
KAFKA_TOPIC      = os.getenv("KAFKA_TOPIC", "bus-gps-raw")
CSV_PATH         = os.getenv("CSV_PATH", "/app/data/processed/bus_gps_clean.csv")
BATCH_SIZE       = int(os.getenv("BATCH_SIZE", "50"))
DELAY_MS         = int(os.getenv("DELAY_MS", "200"))
SPEED_MULTIPLIER = float(os.getenv("SPEED_MULTIPLIER", "1.0"))
LOOP             = os.getenv("LOOP", "false").lower() == "true"


# ── Pause / Resume via SIGUSR1 ───────────────────────────────────────────────
_paused = False


def _toggle_pause(signum, frame):
    global _paused
    _paused = not _paused
    print(f"\n{'='*40}\n  Stream {'PAUSED' if _paused else 'RESUMED'}\n{'='*40}")


if hasattr(signal, "SIGUSR1"):
    signal.signal(signal.SIGUSR1, _toggle_pause)


# ── Kafka ────────────────────────────────────────────────────────────────────
def wait_for_kafka(timeout: int = 120) -> KafkaProducer:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                retries=3,
                linger_ms=10,
                batch_size=16384,
            )
            print(f"Connected to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
            return producer
        except NoBrokersAvailable:
            print("Waiting for Kafka...")
            time.sleep(3)
    print("Kafka not available — exiting.")
    sys.exit(1)


# ── Enrichment ───────────────────────────────────────────────────────────────
def build_enrichment() -> dict[str, dict]:
    """
    Returns a dict: vehicle_hash -> {route_id, route_no, route_name}.
    Cross-joins vehicle_route_mapping.json with routes_clean.json via route_no.
    Vehicles with no match still get route_id and route_no (just no route_name).
    """
    enrichment: dict[str, dict] = {}

    if not os.path.exists(VEHICLE_MAP):
        print(f"  [enrich] {VEHICLE_MAP} not found — skipping enrichment")
        return enrichment

    with open(VEHICLE_MAP, encoding="utf-8") as f:
        vehicle_map: dict = json.load(f)

    # Build route_no → route_name from routes_clean.json
    route_name_lookup: dict[str, str] = {}
    if os.path.exists(ROUTES_FILE):
        with open(ROUTES_FILE, encoding="utf-8") as f:
            routes: list = json.load(f)
        for r in routes:
            info = r.get("Thông tin", {})
            rno = str(info.get("Tuyến số", "")).strip()
            if rno:
                # Use "description" (e.g. "Bến Thành - Suối Tiên") as human-readable name
                name = r.get("description") or r.get("name", "")
                route_name_lookup[rno] = name
        print(f"  [enrich] Loaded {len(route_name_lookup)} routes from routes_clean.json")
    else:
        print(f"  [enrich] {ROUTES_FILE} not found — route names will be omitted")

    for vehicle_hash, info in vehicle_map.items():
        route_no = str(info.get("route_no", "")).strip()
        entry: dict = {
            "route_id": info.get("route_id"),
            "route_no": route_no,
        }
        if route_no in route_name_lookup:
            entry["route_name"] = route_name_lookup[route_no]
        if info.get("plate_no"):
            entry["plate_no"] = info["plate_no"]
        enrichment[vehicle_hash] = entry

    matched = sum(1 for e in enrichment.values() if "route_name" in e)
    print(f"  [enrich] {len(enrichment)} vehicles loaded, "
          f"{matched} with route_name ({len(enrichment)-matched} route_no only)")
    return enrichment


# ── Record builder ───────────────────────────────────────────────────────────
def build_record(
    waypoint: dict,
    shifted_dt: datetime,
    enrichment: dict[str, dict],
) -> dict:
    """Convert a raw msgBusWayPoint dict into a clean, JSON-serialisable record."""
    vehicle = str(waypoint.get("vehicle", "")).strip()

    rec: dict = {
        "vehicle":  vehicle,
        "datetime": shifted_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "lat":      float(waypoint.get("y", 0)),
        "lon":      float(waypoint.get("x", 0)),
        "location": {
            "lat": float(waypoint.get("y", 0)),
            "lon": float(waypoint.get("x", 0)),
        },
    }

    # Optional sensor fields
    for field in ("speed", "heading", "ignition", "aircon", "working",
                  "door_up", "door_down", "driver"):
        val = waypoint.get(field)
        if val is not None:
            rec[field] = val

    # Route enrichment
    if vehicle in enrichment:
        for k, v in enrichment[vehicle].items():
            if v is not None:
                rec[k] = v

    return rec


# ── JSON mode ────────────────────────────────────────────────────────────────
def _natural_sort_key(path: str) -> list:
    """Sort filenames numerically: sub_raw_2 < sub_raw_10 < sub_raw_100."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", os.path.basename(path))]


def find_json_files() -> list[str]:
    # Current expected layout: JSON_DIR/data/*.json
    flat_pattern = os.path.join(JSON_DIR, "data", "*.json")
    files = glob.glob(flat_pattern)
    files = sorted(files, key=_natural_sort_key)

    if MAX_FILES > 0:
        files = files[:MAX_FILES]

    return files


def load_json_file(path: str) -> list[dict]:
    """Load one JSON file and return waypoints sorted by datetime (unix seconds)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [warn] Cannot read {os.path.basename(path)}: {e}")
        return []

    waypoints = []
    for item in data:
        wp = item.get("msgBusWayPoint")
        if wp and wp.get("vehicle") and wp.get("datetime") and wp.get("x") and wp.get("y"):
            wp["vehicle"] = str(wp["vehicle"]).strip()
            waypoints.append(wp)

    waypoints.sort(key=lambda w: w["datetime"])
    return waypoints


def stream_json(
    producer: KafkaProducer,
    files: list[str],
    enrichment: dict[str, dict],
) -> None:
    total_files = len(files)
    total_sent  = 0
    batch: list[dict] = []
    delay_sec = (DELAY_MS / 1000.0) / SPEED_MULTIPLIER
    ts_offset_sec: float | None = None  # unix-second offset so first record = now

    for file_idx, path in enumerate(files, 1):
        waypoints = load_json_file(path)
        if not waypoints:
            continue

        # Compute offset once from the very first record across all files
        if ts_offset_sec is None:
            first_ts = waypoints[0]["datetime"]
            now_ts   = datetime.now(tz=timezone.utc).timestamp()
            ts_offset_sec = now_ts - first_ts
            print(f"  [ts] Shifting timestamps by +{ts_offset_sec/3600:.1f}h "
                  f"(first record → now)")

        print(f"  [file {file_idx}/{total_files}] {os.path.basename(path)} "
              f"— {len(waypoints):,} waypoints")

        for wp in waypoints:
            while _paused:
                time.sleep(0.5)

            shifted_ts = wp["datetime"] + ts_offset_sec
            shifted_dt = datetime.fromtimestamp(shifted_ts, tz=timezone.utc)
            rec = build_record(wp, shifted_dt, enrichment)
            batch.append(rec)

            if len(batch) >= BATCH_SIZE:
                _flush_batch(producer, batch, total_sent)
                total_sent += len(batch)
                batch = []
                time.sleep(delay_sec)

    # Flush remaining
    if batch:
        _flush_batch(producer, batch, total_sent)
        total_sent += len(batch)

    print(f"Done streaming {total_sent:,} records from {total_files} files.")


# ── CSV mode ─────────────────────────────────────────────────────────────────
def load_csv() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        print(f"CSV not found at {CSV_PATH}. Place a pre-processed CSV at that path.")
        sys.exit(1)
    df = pd.read_csv(CSV_PATH)
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
    print(f"Loaded {len(df):,} records from {CSV_PATH}")
    return df


def shift_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    earliest = df["datetime"].min()
    now = datetime.now(tz=timezone.utc)
    if earliest.tzinfo is None:
        earliest = earliest.tz_localize(timezone.utc)
    df["datetime"] = df["datetime"] + (now - earliest)
    return df


def stream_csv(
    producer: KafkaProducer,
    df: pd.DataFrame,
    enrichment: dict[str, dict],
) -> None:
    total = len(df)
    sent  = 0
    batch: list[dict] = []
    delay_sec = (DELAY_MS / 1000.0) / SPEED_MULTIPLIER

    for _, row in df.iterrows():
        while _paused:
            time.sleep(0.5)

        # Convert CSV row to waypoint-style dict
        wp = {
            "vehicle":  str(row["vehicle"]),
            "datetime": None,  # handled separately
            "x":        row.get("x", row.get("lon")),
            "y":        row.get("y", row.get("lat")),
        }
        for col in ("speed", "heading", "ignition", "aircon", "working",
                    "door_up", "door_down", "driver", "route_id", "route_no"):
            val = row.get(col)
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                if hasattr(val, "item"):
                    val = val.item()
                wp[col] = val

        dt = row["datetime"]
        if dt.tzinfo is None:
            dt = dt.tz_localize(timezone.utc)

        rec = build_record(wp, dt, enrichment)
        batch.append(rec)

        if len(batch) >= BATCH_SIZE:
            _flush_batch(producer, batch, sent)
            sent += len(batch)
            pct = round(sent / total * 100, 1)
            print(f"  -> {sent:,}/{total:,} ({pct}%)", end="\r")
            batch = []
            time.sleep(delay_sec)

    if batch:
        _flush_batch(producer, batch, sent)
        sent += len(batch)

    print(f"\nDone streaming {sent:,} records from CSV.")


# ── Shared helpers ────────────────────────────────────────────────────────────
def _flush_batch(producer: KafkaProducer, batch: list[dict], sent_so_far: int) -> None:
    for rec in batch:
        producer.send(KAFKA_TOPIC, key=rec.get("vehicle"), value=rec)
    producer.flush()


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 62)
    print("  Smart Bus GPS Simulator → Kafka Producer")
    print(f"  Mode     : {DATA_MODE.upper()}")
    print(f"  Kafka    : {KAFKA_BOOTSTRAP_SERVERS}")
    print(f"  Topic    : {KAFKA_TOPIC}")
    if DATA_MODE == "json":
        print(f"  JSON dir : {JSON_DIR}")
        print(f"  Max files: {'all' if MAX_FILES == 0 else MAX_FILES}")
    else:
        print(f"  CSV      : {CSV_PATH}")
    print(f"  Batch    : {BATCH_SIZE} records / {DELAY_MS}ms  (speed {SPEED_MULTIPLIER}x)")
    print(f"  Loop     : {LOOP}")
    print(f"  Pause    : kill -SIGUSR1 <pid>")
    print("=" * 62)

    producer = wait_for_kafka()

    print("Loading enrichment table...")
    enrichment = build_enrichment()

    if DATA_MODE == "json":
        files = find_json_files()
        if not files:
            print(
                f"No JSON files found under {JSON_DIR}/data/*.json — exiting."
            )
            sys.exit(1)
        print(f"Found {len(files)} JSON files to process.")

        while True:
            stream_json(producer, files, enrichment)
            if not LOOP:
                break
            print("Restarting (LOOP=true)...")
            # Reset timestamp offset on restart by passing fresh list
    else:
        df = load_csv()
        df = shift_timestamps(df)
        while True:
            stream_csv(producer, df, enrichment)
            if not LOOP:
                break
            print("Restarting (LOOP=true)...")
            df = shift_timestamps(df)

    producer.close()


if __name__ == "__main__":
    main()
