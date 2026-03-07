"""Convert vehicle_route_mapping.csv to JSON format."""
import json
import csv
from pathlib import Path

CSV_PATH = Path("data/raw/vehicle_route_mapping.csv")
JSON_PATH = Path("data/raw/vehicle_route_mapping.json")


def main():
    """Convert CSV to JSON with vehicle as key."""

    if not CSV_PATH.exists():
        print(f"Error: {CSV_PATH} not found")
        return

    # Option 1: Dictionary với vehicle làm key (tra cứu nhanh)
    vehicle_map = {}

    with open(CSV_PATH, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            vehicle_id = row['vehicle']
            vehicle_map[vehicle_id] = {
                'route_id': int(row['route_id']),
                'route_no': row['route_no']
            }

    # Save JSON
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(vehicle_map, f, indent=2, ensure_ascii=False)

    print(f"✅ Converted {len(vehicle_map)} vehicles")
    print(f"📄 Saved to: {JSON_PATH}")

    # Show sample
    sample = list(vehicle_map.items())[:3]
    print("\nSample data:")
    for vehicle, info in sample:
        print(f"  {vehicle[:20]}... → Route {info['route_no']} (ID: {info['route_id']})")


if __name__ == "__main__":
    main()
