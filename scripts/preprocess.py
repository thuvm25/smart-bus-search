from pathlib import Path
import json
import glob
import os

import pandas as pd


RAW_PARTS_DIR = Path("data/raw")
PROCESSED_PATH = Path("data/processed/bus_gps_clean.csv")
PROCESS_FULL_DATASET = os.getenv("PROCESS_FULL_DATASET", "false").lower() == "true"


def main() -> None:
    """Load and preprocess bus GPS waypoints from JSON files.

    By default, uses data/raw/sample.json (~214k records).
    Set env var PROCESS_FULL_DATASET=true to process all raw files.
    Preferred layout: data/raw/data/*.json (flat).
    Legacy layout is still supported: data/raw/part*/part*/*.json.
    """

    # Default: use sample.json for faster development
    if not PROCESS_FULL_DATASET:
        json_files = ["data/raw/sample.json"]
        print("Using sample.json for quick development (~214k records)")
        print("To process full dataset, run: PROCESS_FULL_DATASET=true python scripts/preprocess.py")
    else:
        # Preferred full dataset layout: flat data/raw/data/*.json
        json_files = sorted(glob.glob("data/raw/data/*.json"))
        if not json_files:
            # Backward compatibility: all sub_raw_*.json from part1/part2
            json_files = sorted(glob.glob("data/raw/part*/part*/*.json"))
        print(f"⚠️ Processing FULL dataset: {len(json_files)} JSON files (may take 10-30 minutes)")

    if not json_files:
        raise FileNotFoundError(
            "Không tìm thấy file JSON trong data/raw. "
            "Hãy download dataset từ Kaggle."
        )

    all_records = []
    for i, json_file in enumerate(json_files, 1):
        if len(json_files) > 10 and i % 50 == 0:
            print(f"Processed {i}/{len(json_files)} files...")

        try:
            with open(json_file, 'r') as f:
                data = json.load(f)

            # Extract waypoints from JSON structure
            if isinstance(data, list):
                for item in data:
                    if "msgBusWayPoint" in item:
                        waypoint = item["msgBusWayPoint"]
                        # Clean up vehicle ID
                        waypoint["vehicle"] = waypoint.get("vehicle", "").strip()
                        all_records.append(waypoint)
        except Exception as e:
            print(f"Warning: Error reading {json_file}: {e}")
            continue

    if not all_records:
        raise ValueError("Không tìm thấy msgBusWayPoint trong JSON files")

    df = pd.DataFrame(all_records)
    print(f"Loaded {len(df)} records from {len(json_files)} files")

    # Validate required columns
    required_cols = {"vehicle", "datetime", "x", "y"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"Thiếu các cột bắt buộc: {', '.join(sorted(missing))}\n"
            f"Có sẵn: {', '.join(sorted(df.columns))}"
        )

    # Clean data
    df = df.dropna(subset=["vehicle", "datetime", "x", "y"])

    # Convert datetime - handle both Unix timestamp and string format
    if pd.api.types.is_numeric_dtype(df["datetime"]):
        # Unix timestamp (seconds or milliseconds)
        if df["datetime"].max() > 1e10:  # likely milliseconds
            df["datetime"] = pd.to_datetime(df["datetime"], unit="ms")
        else:
            df["datetime"] = pd.to_datetime(df["datetime"], unit="s")
    else:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")

    df = df.dropna(subset=["datetime"])

    # Keep only essential columns for Elasticsearch.
    # Keep route_id for filtering/aggregation; avoid route_name duplication in large datasets.
    extra_cols = {
        "speed",
        "ignition",
        "aircon",
        "working",
        "driver",
        "route_id",
        "route_no",
        "stop_name",
    }
    essential_cols = list(required_cols) + [
        col for col in df.columns if col not in required_cols and col in extra_cols
    ]
    df = df[[col for col in essential_cols if col in df.columns]]

    PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_PATH, index=False)
    print(f"✓ Đã lưu {len(df)} records vào {PROCESSED_PATH}")


if __name__ == "__main__":
    main()

