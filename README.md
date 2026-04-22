# Smart Bus GPS Search

Hệ thống giả lập streaming dữ liệu GPS xe buýt TP.HCM qua pipeline đầy đủ từ nguồn đến giao diện:

```
Data (JSON) → Simulator → Kafka → Logstash → Elasticsearch → FastAPI → Streamlit UI
                                                                  └──────→ Kibana
```

Dữ liệu gốc là historical data (~104M GPS records), được simulate thành real-time streaming và hiển thị trên 2 lớp frontend: Kibana (analytics) và Streamlit (custom dashboard).

## Chạy nhanh (TL;DR)

```bash
# 1) Khởi động toàn bộ stack
docker compose --profile simulate up -d --build

# 2) Setup index + Kibana (chỉ chạy 1 lần duy nhất, sau khi ES healthy)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/create_index.py 
python scripts/setup_kibana.py
python scripts/setup_kibana_map.py

# Kiểm tra dữ liệu vào ES
curl -s http://localhost:9200/bus_waypoints/_count
```

> **Lần sau** chỉ cần: `docker compose --profile simulate up -d`  
> Không cần chạy lại bước 2 trừ khi xoá volume (`docker compose down -v`).

## Các địa chỉ truy cập

| Service | URL | Mô tả |
|---------|-----|-------|
| Streamlit UI | http://localhost:8501 | Dashboard tìm kiếm & live map |
| Backend API | http://localhost:8000/docs | Swagger UI |
| Kibana | http://localhost:5601 | Analytics & Maps |
| Elasticsearch | http://localhost:9200 | Storage & search |

## Kiến trúc

```
┌───────────┐    ┌─────────┐    ┌──────────┐    ┌───────────────┐
│ Simulator │───▶│  Kafka  │───▶│ Logstash │───▶│ Elasticsearch │
│(Producer) │    │(Broker) │    │  (ETL)   │    │  (Storage)    │
└───────────┘    └─────────┘    └──────────┘    └───────┬───────┘
  Đọc JSON,        Buffer        Parse JSON,             │
  enrich route,    topic:        geo_point,              ├──────▶ Kibana :5601
  shift timestamp  bus-gps-raw   @timestamp              │        Dashboard + Maps
  → batch Kafka                  → index ES              │
                                                         └──────▶ FastAPI :8000
                                                                  /api/livebus
                                                                  /api/fuzzysearch
                                                                       │
                                                                       ▼
                                                                  Streamlit :8501
                                                                  Live map + Route search
```

## Yêu cầu

- **Docker Desktop** ≥ 4.x (cấp ít nhất **6 GB RAM** trong Docker Desktop Settings)
- **Python 3.9+** (chỉ dùng cho scripts setup một lần)

## Hướng dẫn cài đặt

### Bước 0 — Clone & chuẩn bị data

```bash
git clone <repo-url>
cd smart-bus-search
```

Đặt các file GPS JSON vào đúng layout:

```
data/raw/
├── data/                          ← sub_raw_*.json đặt vào đây
│   ├── sub_raw_1.json
│   └── ...
├── vehicle_route_mapping.json     ← có sẵn trong repo
└── routes_clean.json              ← có sẵn trong repo
```

Nếu có file nén `hcmut-gps.zip`:

```bash
mkdir -p data/raw/data
unzip -o hcmut-gps.zip "part1/*" "part2/*" -d data/raw
mv data/raw/part1/part1/*.json data/raw/data/ 2>/dev/null
mv data/raw/part2/part2/*.json data/raw/data/ 2>/dev/null
rm -rf data/raw/part1 data/raw/part2
```

### Bước 1 — Khởi động toàn bộ stack

```bash
docker compose --profile simulate up -d --build
```

Đợi ~1–2 phút để tất cả services healthy. Tất cả services (Kafka, Elasticsearch, Kibana, Logstash, Simulator, FastAPI, Streamlit) đều chạy trong Docker.

### Bước 2 — Tạo index ES & saved objects Kibana

Chạy **một lần duy nhất** sau khi Elasticsearch healthy:

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scripts/create_index.py      # tạo index bus_waypoints + geo_point mapping
python scripts/setup_kibana.py      # Data View + Dashboard + visualizations
python scripts/setup_kibana_map.py  # Kibana Maps (live map + heatmap)
```

### Bước 3 — Truy cập

| Địa chỉ | Nội dung |
|---------|----------|
| http://localhost:8501 | Streamlit — live map + tìm kiếm tuyến xe |
| http://localhost:8000/docs | FastAPI — Swagger UI |
| http://localhost:5601/app/dashboards#/view/smart-bus-dashboard | Kibana Dashboard |
| http://localhost:5601/app/maps/map/smart-bus-live-map | Kibana Maps live |

## Kiểm tra từng chặng

```bash
# ES có dữ liệu?
curl -s http://localhost:9200/bus_waypoints/_count

# Backend API hoạt động?
curl -s http://localhost:8000/health

# Simulator đang phát?
docker logs -f smart-bus-simulator

# Logstash đang consume + đẩy ES?
docker logs -f smart-bus-logstash
```

## Cấu hình Simulator

| Variable | Default | Mô tả |
|----------|---------|-------|
| `BATCH_SIZE` | `50` | Số records mỗi batch gửi Kafka |
| `DELAY_MS` | `200` | Khoảng cách giữa các batch (ms) |
| `SPEED_MULTIPLIER` | `1.0` | Hệ số tốc độ phát (2.0 = nhanh gấp đôi) |
| `LOOP` | `false` | Lặp lại từ đầu khi hết dữ liệu |
| `MAX_FILES` | `0` | Giới hạn số file JSON xử lý (0 = tất cả) |

Pause / Resume stream:

```bash
docker kill --signal=SIGUSR1 smart-bus-simulator
```

## Dừng hệ thống

```bash
# Dừng (giữ data ES)
docker compose --profile simulate down

# Dừng + xóa toàn bộ data ES
docker compose --profile simulate down -v
```

## Development — chỉnh code không cần restart Docker

- **Backend** (`backend/`): uvicorn chạy với `--reload`, save file là tự restart.
- **UI** (`ui/`): Streamlit chạy với `--server.runOnSave true`, save file là tự reload.
- Chỉ cần `--build` lại khi thêm package vào `requirements.txt`.

## Cấu trúc thư mục

```
├── backend/                          ← FastAPI REST API
│   ├── Dockerfile
│   └── app/
│       ├── main.py                   ← app entry point, CORS, health check
│       ├── core/es_client.py         ← Elasticsearch client singleton
│       └── routers/
│           ├── livebus.py            ← GET /api/livebus (GeoJSON positions)
│           └── fuzzysearch.py        ← GET /api/fuzzysearch (route search)
│
├── ui/
│   ├── Dockerfile
│   └── smartsearchbus_web.py         ← Streamlit dashboard
│
├── simulator/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── simulate_gps.py               ← Kafka producer
│
├── logstash/
│   ├── config/logstash.yml
│   └── pipeline/kafka-to-es.conf     ← ETL: Kafka → parse → Elasticsearch
│
├── scripts/
│   ├── create_index.py               ← tạo ES index với geo_point mapping
│   ├── setup_kibana.py               ← Data View + Dashboard + visualizations
│   └── setup_kibana_map.py           ← Kibana Maps saved object
│
├── kibana/kibana.yml
├── data/
│   ├── raw/
│   │   ├── data/                     ← sub_raw_*.json (simulator đọc từ đây)
│   │   ├── vehicle_route_mapping.json
│   │   └── routes_clean.json
│   └── processed/
│
├── requirements.txt                  ← deps cho backend, UI, scripts
└── docker-compose.yml
```

## Lưu ý khi demo

- Timestamp được shift về "bây giờ" → biểu đồ Kibana và map trông như real-time
- Tăng `SPEED_MULTIPLIER` hoặc giảm `DELAY_MS` để demo nhanh hơn
- Base map dùng OpenStreetMap — không cần Elastic Maps Service license
