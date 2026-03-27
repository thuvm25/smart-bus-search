# Smart Bus GPS — Real-time Streaming Pipeline

Hệ thống giả lập streaming dữ liệu GPS xe buýt TP.HCM qua pipeline:

```
Data (JSON) → Simulator → Kafka → Logstash → Elasticsearch → Kibana
```

Dữ liệu gốc là historical data (JSON files), được simulate thành real-time streaming để demo hệ thống.

## Kiến trúc

```
┌─────────────┐     ┌─────────┐     ┌───────────┐     ┌───────────────┐     ┌────────┐
│  Simulator   │────▶│  Kafka  │────▶│ Logstash  │────▶│ Elasticsearch │────▶│ Kibana │
│ (Producer)   │     │ (Broker)│     │  (ETL)    │     │  (Storage)    │     │ (Viz)  │
└─────────────┘     └─────────┘     └───────────┘     └───────────────┘     └────────┘
  Đọc JSON files,    Buffer          Parse JSON,       Lưu trữ &           Dashboard
  shift timestamp,   messages        add @timestamp,   index data           realtime
  gửi từng batch                     build geo_point,
  vào topic                          đẩy vào ES
  bus-gps-raw
```

## Yêu cầu

- **Docker Desktop** (bao gồm Docker Compose)
- **Python 3.9+** (chỉ cần để chạy scripts setup, không cần cho pipeline chính)
- RAM tối thiểu: **6 GB** (cho Kafka + Zookeeper + ES + Logstash + Kibana)

## Hướng dẫn nhanh

### Bước 1 — Clone & chuẩn bị data

```bash
git clone <repo-url>
cd smart-bus-search
``` 
### Bước 2 — Khởi động hệ thống

```bash
docker compose up --build -d
```

Đợi ~1-2 phút để tất cả services khởi động.

| Service        | URL                    | Mô tả                      |
|----------------|------------------------|-----------------------------|
| Kafka          | localhost:29092        | Message broker              |
| Elasticsearch  | http://localhost:9200  | Storage & search engine     |
| Kibana         | http://localhost:5601  | Dashboard & visualization   |
| Logstash       | (internal)             | Kafka → ES pipeline         |

### Bước 3 — Tạo ES index & Kibana dashboards

```bash
cd scripts
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python create_index.py             # tạo index bus_waypoints với geo_point mapping
python setup_kibana.py             # tạo Data View + Dashboard + Visualizations
python setup_kibana_map.py         # tạo Kibana Maps (live map + heatmap)
```

### Bước 4 — Chạy Simulator (giả lập real-time)

```bash
docker compose --profile simulate up simulator --build
```

Simulator sẽ:
- Đọc JSON files từ `data/raw/` theo thứ tự timestamp
- Enrich mỗi record với thông tin tuyến (route_id, route_no, route_name)
- Shift timestamp về "now" để dữ liệu cũ hiển thị như real-time
- Gửi từng batch vào Kafka topic `bus-gps-raw`
- Logstash consume và đẩy vào Elasticsearch tự động
- Kibana hiển thị data update liên tục

### Bước 5 — Xem Dashboard

Truy cập http://localhost:5601 và mở:

| URL | Nội dung |
|-----|----------|
| `/app/dashboards#/view/smart-bus-dashboard` | Dashboard tổng hợp real-time |
| `/app/maps/map/smart-bus-live-map` | Bản đồ GPS + Heatmap mật độ |

## Cấu hình Simulator

| Variable            | Default   | Mô tả                                 |
|---------------------|-----------|----------------------------------------|
| `DATA_MODE`         | `json`    | `json` = đọc JSON files; `csv` = đọc CSV (legacy) |
| `BATCH_SIZE`        | `50`      | Số records mỗi batch gửi vào Kafka    |
| `DELAY_MS`          | `200`     | Milliseconds giữa các batch           |
| `SPEED_MULTIPLIER`  | `1.0`     | Tốc độ phát (2.0 = nhanh gấp đôi)    |
| `LOOP`              | `false`   | Lặp lại khi hết dữ liệu              |
| `MAX_FILES`         | `0`       | Số file JSON tối đa (0 = tất cả)     |

### Điều khiển khi đang chạy

```bash
# Pause / Resume stream
docker kill --signal=SIGUSR1 smart-bus-simulator

# Tăng tốc: sửa SPEED_MULTIPLIER trong docker-compose.yml rồi restart simulator
```

## Dừng hệ thống

```bash
# Dừng (giữ data ES)
docker compose --profile simulate down

# Dừng + xóa toàn bộ data ES
docker compose --profile simulate down -v
```

## Cấu trúc thư mục

```
├── data/
│   ├── raw/                          # dataset gốc (JSON từ HPCC)
│   │   ├── data/                     # các file sub_raw_*.json
│   │   ├── vehicle_route_mapping.json
│   │   └── routes_clean.json
│   └── processed/                    # CSV (chỉ dùng khi DATA_MODE=csv)
│
├── scripts/
│   ├── create_index.py               # tạo ES index với geo_point mapping
│   ├── setup_kibana.py               # tạo Data View, Dashboard, Visualizations
│   ├── setup_kibana_map.py           # tạo Kibana Maps (live map + heatmap)
│   ├── preprocess.py                 # JSON → CSV (chỉ cần cho DATA_MODE=csv)
│   └── ingest_bus_gps.py             # bulk ingest CSV vào ES (bypass Kafka)
│
├── simulator/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── simulate_gps.py              # Kafka producer — đọc JSON, enrich, stream
│
├── logstash/
│   ├── config/
│   │   └── logstash.yml
│   └── pipeline/
│       └── kafka-to-es.conf         # Kafka → ES: parse JSON, @timestamp, geo_point
│
├── kibana/
│   └── kibana.yml                 
│
└── docker-compose.yml               # Zookeeper + Kafka + ES + Logstash + Kibana + Simulator
```

## Kibana Dashboard

Sau khi chạy `setup_kibana.py` và `setup_kibana_map.py`, các visualization có sẵn:

| Panel | Loại | Mô tả |
|-------|------|-------|
| 📡 Total GPS Pings | Metric | Tổng số GPS records |
| 🚌 Active Vehicles | Metric | Số xe đang hoạt động |
| ⏱ GPS Pings / Minute | Bar chart | Tần suất theo thời gian |
| 🗺 Bus Positions | Vega map | Vị trí xe real-time (OSM, màu theo tốc độ) |
| 🚀 Speed Distribution | Histogram | Phân bổ tốc độ |
| 🗺 Top Routes by Pings | Donut chart | Tuyến xe nhiều GPS nhất |
| 🌡 GPS Density Heatmap | Kibana Maps | Mật độ GPS theo khu vực |
| 🛣 Vehicle Trajectory | Data table | Thống kê từng xe |

## Lưu ý khi demo

- Dữ liệu cũ nhưng timestamp được shift về "now" → hiển thị như real-time
- Dashboard Kibana auto-refresh mỗi 5 giây
- Có thể pause/resume stream bất cứ lúc nào
- Tăng `SPEED_MULTIPLIER` để demo nhanh hơn
- Base map dùng OpenStreetMap (không cần Elastic Maps Service)

## Chế độ CSV (legacy / bypass Kafka)

Nếu không dùng Kafka và muốn nạp data thẳng vào ES:

```bash
# 1. Tiền xử lý JSON → CSV
python scripts/preprocess.py

# 2. Nạp CSV vào ES (bypass pipeline)
python scripts/ingest_bus_gps.py
```

Hoặc chạy simulator ở chế độ CSV:
```yaml
# docker-compose.yml
simulator:
  environment:
    DATA_MODE: "csv"
    CSV_PATH: /app/data/processed/bus_gps_clean.csv
```
