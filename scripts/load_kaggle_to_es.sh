#!/usr/bin/env bash
set -euo pipefail

DATASET="thuvm2502/hcmut-gps"
RAW_DIR="data/raw"
RAW_CSV="${RAW_DIR}/bus_gps.csv"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed." >&2
  exit 1
fi

if [[ ! -f "kaggle.json" ]]; then
  echo "Missing kaggle.json at project root." >&2
  echo "Place your Kaggle API key file at ./kaggle.json and run again." >&2
  exit 1
fi

echo "Starting Elasticsearch container..."
docker compose up -d elasticsearch

mkdir -p "${RAW_DIR}" data/processed

echo "Downloading dataset from Kaggle and ingesting to Elasticsearch..."
docker run --rm \
  -e DATASET="${DATASET}" \
  -e RAW_DIR="${RAW_DIR}" \
  -e RAW_CSV="${RAW_CSV}" \
  -v "${PWD}:/workspace" \
  -w /workspace \
  python:3.11-slim \
  sh -lc '
    set -e
    pip install --no-cache-dir kaggle pandas python-dotenv "elasticsearch>=8.0,<9.0" >/dev/null

    mkdir -p /root/.kaggle
    cp kaggle.json /root/.kaggle/kaggle.json
    chmod 600 /root/.kaggle/kaggle.json

    kaggle datasets download -d "${DATASET}" -p "${RAW_DIR}" --unzip

    if [ ! -f "${RAW_CSV}" ]; then
      first_csv=$(find "${RAW_DIR}" -maxdepth 1 -type f -name "*.csv" | head -n 1)
      if [ -z "${first_csv}" ]; then
        echo "No CSV file found in ${RAW_DIR} after download." >&2
        exit 1
      fi
      cp "${first_csv}" "${RAW_CSV}"
    fi

    python scripts/preprocess.py
    ES_HOST=http://host.docker.internal:9200 python scripts/create_index.py
    ES_HOST=http://host.docker.internal:9200 python scripts/ingest_bus_gps.py
  '

echo "Done. Data is now in Elasticsearch index bus_waypoints."
echo "Try: http://localhost:8000/docs"
