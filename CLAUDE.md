# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Smart Bus GPS** is a real-time IoT streaming pipeline that simulates live GPS tracking from Ho Chi Minh City buses. It replays ~104M+ historical GPS records as a real-time stream through a full big data stack.

**Data flow:**
```
JSON files → Python Simulator → Kafka → Logstash → Elasticsearch → Kibana
```

## Running the Stack

### Full fresh setup
```bash
# Start core services (Zookeeper, Kafka, Elasticsearch, Kibana, Logstash)
docker compose build --no-cache
docker compose up -d

# Wait ~1-2 minutes for services to be healthy, then initialize
python3 -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt
python scripts/create_index.py
python scripts/setup_kibana.py
python scripts/setup_kibana_map.py

# Start the GPS simulator (separate Docker profile)
docker compose --profile simulate build --no-cache simulator
docker compose --profile simulate up simulator -d
```

### Common operations
```bash
# Check data is flowing
curl -s http://localhost:9200/bus_waypoints/_count

# View logs
docker logs -f smart-bus-simulator
docker logs -f smart-bus-logstash

# Pause/resume simulator (SIGUSR1 toggles)
docker kill --signal=SIGUSR1 smart-bus-simulator

# Stop (keep data)
docker compose --profile simulate down

# Stop and wipe all data
docker compose --profile simulate down -v
```

### Access points
- Kibana: http://localhost:5601
- Elasticsearch: http://localhost:9200

## Architecture

### Services (docker-compose.yml)
| Service | Image | Port | Role |
|---------|-------|------|------|
| zookeeper | confluentinc/cp-zookeeper:7.6.0 | — | Kafka coordination |
| kafka | confluentinc/cp-kafka:7.6.0 | 29092 | Message broker, topic `bus-gps-raw` |
| elasticsearch | elastic 8.15.0 | 9200 | Storage + search, index `bus_waypoints` |
| kibana | elastic 8.15.0 | 5601 | Visualization |
| logstash | elastic 8.15.0 | — | ETL: Kafka → Elasticsearch |
| simulator | python:3.11 | — | Data producer (profile: `simulate`) |

### Key source files
- `simulator/simulate_gps.py` — Reads JSON files, enriches with route data (vehicle → route_name), shifts timestamps to "now", sends batches to Kafka
- `logstash/pipeline/kafka-to-es.conf` — Parses ISO8601 timestamps, coerces types, builds `location` geo_point, removes Kafka metadata, indexes to ES
- `scripts/create_index.py` — Creates `bus_waypoints` ES index with `location` as `geo_point` mapping (must run before simulator)
- `scripts/setup_kibana.py` — Creates Data View (`bus_waypoints_dv`), visualizations, dashboard
- `scripts/setup_kibana_map.py` — Configures Kibana Maps layers for live GPS tracking

### Data enrichment files
- `data/raw/vehicle_route_mapping.json` — vehicle hash → `{route_id, route_no}`
- `data/raw/routes_clean.json` — route_no → `{name, description, stops}`
- `data/raw/data/sub_raw_*.json` — ~517 input files, each containing arrays of `{msgBusWayPoint: {...}}` objects

### Elasticsearch record structure
After Logstash processing, records contain: `vehicle`, `datetime`, `lat`, `lon`, `location` (geo_point), `speed`, `heading`, `ignition`, `aircon`, `route_id`, `route_no`, `route_name`, `@timestamp`.

## Simulator Configuration (environment variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_MODE` | `json` | `json` = read files, `csv` = pre-processed CSV |
| `BATCH_SIZE` | `50` | Records per Kafka batch |
| `DELAY_MS` | `200` | Milliseconds between batches |
| `SPEED_MULTIPLIER` | `1.0` | Playback speed (2.0 = 2× faster) |
| `LOOP` | `false` | Restart from beginning when data exhausted |
| `MAX_FILES` | `0` | Max JSON files to process (0 = all) |

## Important Notes

- The `es-data` Docker volume persists Elasticsearch data between restarts. Use `-v` flag to wipe it.
- The simulator uses the `simulate` Docker Compose profile — it does not start with plain `docker compose up`.
- Kibana is configured to use OpenStreetMap tiles (not Elastic Maps Service) — see `kibana/kibana.yml`.
- The ES index must exist before starting the simulator. Running `create_index.py` twice is safe (idempotent).
- Logstash pipeline workers = 2, batch size = 500 (`logstash/config/logstash.yml`).
