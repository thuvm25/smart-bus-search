#!/usr/bin/env bash
set -euo pipefail

# Run enrichment script in an ephemeral Python container.
# Usage:
#   ./scripts/run_enrich_gps_with_routes.sh \
#     --gps-path data/raw/sample.json \
#     --stops-path bus_stops.json \
#     --output-path data/processed/bus_gps_enriched.csv \
#     --threshold-m 100 \
#     --chunk-size 2000

docker run --rm \
  -v "$PWD":/app \
  -w /app \
  python:3.11-slim \
  bash -lc "pip -q install pandas numpy && python scripts/enrich_gps_with_routes.py $*"
