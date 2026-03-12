"""
GPS Simulator — reads a static CSV and streams records to the backend API,
imitating real-time IoT GPS devices sending data.

Flow:
  1. Load cleaned CSV (sorted by datetime).
  2. Shift all timestamps so the earliest record maps to "now".
  3. Send records in batches to POST /api/ingest/batch.
  4. Sleep between batches to mimic real-time cadence.

Environment variables (set in docker-compose):
  BACKEND_URL   – e.g. http://backend:8000
  CSV_PATH      – path to the processed CSV
  BATCH_SIZE    – how many records per API call (default 200)
  SEND_INTERVAL – seconds between batches     (default 2)
  LOOP          – "true" to restart when CSV is exhausted
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
CSV_PATH = os.getenv("CSV_PATH", "data/processed/bus_gps_clean.csv")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "200"))
SEND_INTERVAL = float(os.getenv("SEND_INTERVAL", "2"))
LOOP = os.getenv("LOOP", "false").lower() == "true"

INGEST_URL = f"{BACKEND_URL}/api/ingest/batch"


def wait_for_backend(timeout: int = 120) -> None:
    url = f"{BACKEND_URL}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                print(f"Backend is ready at {BACKEND_URL}")
                return
        except requests.ConnectionError:
            pass
        time.sleep(2)
    print("Backend did not become ready in time — starting anyway.")


def load_csv() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        print(f"CSV not found at {CSV_PATH}")
        print("Run  python scripts/preprocess.py  first.")
        sys.exit(1)

    df = pd.read_csv(CSV_PATH)
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
    print(f"Loaded {len(df)} records from {CSV_PATH}")
    return df


def shift_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Shift all timestamps so the earliest record = now."""
    earliest = df["datetime"].min()
    offset = datetime.now(tz=timezone.utc) - earliest.tz_localize(timezone.utc) if earliest.tzinfo is None else datetime.now(tz=timezone.utc) - earliest
    df["datetime"] = df["datetime"] + offset
    return df


def send_batch(rows: list[dict]) -> None:
    payload = {"waypoints": rows}
    try:
        r = requests.post(INGEST_URL, json=payload, timeout=15)
        body = r.json()
        print(
            f"  -> sent {len(rows)} records | "
            f"indexed={body.get('indexed')} took={body.get('took_ms')}ms"
        )
    except Exception as exc:
        print(f"  !! send error: {exc}")


def build_waypoint(row: pd.Series) -> dict:
    wp: dict = {
        "vehicle": str(row["vehicle"]),
        "datetime": row["datetime"].isoformat(),
        "lat": float(row["y"]),
        "lon": float(row["x"]),
    }
    for col in ("speed", "ignition", "aircon", "heading", "door_up", "door_down",
                "route_id", "route_no"):
        val = row.get(col)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            wp[col] = val
    return wp


def stream(df: pd.DataFrame) -> None:
    total = len(df)
    sent = 0
    batch: list[dict] = []

    for _, row in df.iterrows():
        batch.append(build_waypoint(row))
        if len(batch) >= BATCH_SIZE:
            send_batch(batch)
            sent += len(batch)
            batch = []
            pct = round(sent / total * 100, 1)
            print(f"Progress: {sent}/{total} ({pct}%)")
            time.sleep(SEND_INTERVAL)

    if batch:
        send_batch(batch)
        sent += len(batch)

    print(f"Done streaming {sent} records.")


def main() -> None:
    print("=" * 60)
    print("  Smart Bus GPS Simulator")
    print(f"  Backend : {BACKEND_URL}")
    print(f"  CSV     : {CSV_PATH}")
    print(f"  Batch   : {BATCH_SIZE} records")
    print(f"  Interval: {SEND_INTERVAL}s between batches")
    print(f"  Loop    : {LOOP}")
    print("=" * 60)

    wait_for_backend()
    df = load_csv()
    df = shift_timestamps(df)

    while True:
        stream(df)
        if not LOOP:
            break
        print("Restarting from beginning (LOOP=true) ...")
        df = shift_timestamps(df)


if __name__ == "__main__":
    main()
