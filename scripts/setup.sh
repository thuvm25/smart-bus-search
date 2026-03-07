#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "Smart Bus Search - Setup & Data Loading"
echo "=========================================="
echo ""

if ! command -v docker >/dev/null 2>&1; then
  echo "❌ Docker is not installed or not in PATH." >&2
  exit 1
fi

echo "✓ Docker found"

# Check Kaggle API key
if [[ ! -f "kaggle.json" ]]; then
  echo ""
  echo "⚠️  kaggle.json not found at project root."
  echo "   To download data from Kaggle, you need:"
  echo "   1. Go to https://www.kaggle.com/settings/account"
  echo "   2. Download your API key (kaggle.json)"
  echo "   3. Place it at: ./kaggle.json"
  echo ""
  read -p "Do you want to continue without downloading data? (y/n) " -n 1 -r
  echo ""
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
  SKIP_DATA_LOAD=1
else
  echo "✓ kaggle.json found"
  SKIP_DATA_LOAD=0
fi

echo ""
echo "Starting Docker services..."
docker compose up -d elasticsearch backend
echo "✓ Elasticsearch and backend are running"

echo ""
if [[ $SKIP_DATA_LOAD -eq 0 ]]; then
  echo "Loading data from Kaggle..."
  ./scripts/load_kaggle_to_es.sh
  echo "✓ Data loading complete"
else
  echo "⚠️  Skipped data loading (no kaggle.json)"
  echo "   To load data later, run:"
  echo "   ./scripts/load_kaggle_to_es.sh"
fi

echo ""
echo "=========================================="
echo "✓ Setup complete!"
echo "=========================================="
echo ""
echo "Services are running at:"
echo "  • FastAPI docs: http://localhost:8000/docs"
echo "  • Elasticsearch: http://localhost:9200"
echo "  • Streamlit UI: http://localhost:8501 (if running 'docker compose up ui')"
echo ""
echo "To check data was loaded:"
echo "  curl http://localhost:9200/bus_waypoints/_count"
echo ""
echo "To stop services:"
echo "  docker compose down"
echo ""
