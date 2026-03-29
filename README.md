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
  Đọc JSON trong     Buffer          Parse JSON,       Lưu trữ &           Dashboard
  data/raw/data/,   messages        add @timestamp,   index data           (query ES)
  shift timestamp,                 build geo_point,
  gửi batch vào                    đẩy vào ES
  topic bus-gps-raw
```

## Yêu cầu

- **Docker Desktop** (bao gồm Docker Compose)
- **Python 3.9+** (chỉ để chạy scripts setup: tạo index, setup Kibana)
- RAM tối thiểu: **6 GB** (Zookeeper + Kafka + ES + Logstash + Kibana)

### Chạy từ đầu đến Kibana — build lại Docker từ đầu

Dùng khi muốn **dừng hết stack**, **xóa volume Elasticsearch** (mất dữ liệu index cũ), **build lại image không dùng cache**, rồi chạy lại toàn bộ. Thực hiện **từ thư mục gốc repo** (đã `git clone` và `cd` vào đó).

```bash
# 0) Dừng simulator (nếu có) + core, xóa volume ES
docker compose --profile simulate down -v

# 1) (Tuỳ chọn) Giải nén dataset — bỏ qua nếu data/raw/data/ đã có file *.json
# mkdir -p data/raw/data
# unzip -o hcmut-gps.zip "part1/*" "part2/*" -d data/raw
# mv data/raw/part1/part1/*.json data/raw/data/ 2>/dev/null
# mv data/raw/part2/part2/*.json data/raw/data/ 2>/dev/null
# rm -rf data/raw/part1 data/raw/part2

# 2) Build lại toàn bộ image + bật Zookeeper, Kafka, ES, Logstash, Kibana
docker compose build --no-cache
docker compose up -d

# 3) Đợi ~1–2 phút (ES/Kafka healthy). Tạo index + saved objects Kibana
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r scripts/requirements.txt
python scripts/create_index.py
python scripts/setup_kibana.py
python scripts/setup_kibana_map.py

# 4) Build lại image simulator + chạy nền
docker compose --profile simulate build --no-cache simulator
docker compose --profile simulate up simulator -d

# 5) Kiểm tra + mở Kibana
curl -s http://localhost:9200/bus_waypoints/_count
# http://localhost:5601  →  dashboard / map (xem bước 4 phía dưới)
```

> **Không** cần `--no-cache` mỗi lần chỉnh code nhỏ: khi đó thường chỉ `docker compose up --build -d` là đủ. `--no-cache` dùng khi muốn build sạch hoàn toàn (Dockerfile / base image đổi mạnh).

## Hướng dẫn nhanh

### Bước 0 — Clone & chuẩn bị data

```bash
git clone <repo-url>
cd smart-bus-search
```

Đặt data vào đúng layout:

```
data/raw/
├── data/                          ← các file sub_raw_*.json đặt vào đây
│   ├── sub_raw_1.json
│   └── ...
├── vehicle_route_mapping.json     ← enrich xe → tuyến (tùy chọn, có sẵn trong repo)
└── routes_clean.json              ← tên tuyến (tùy chọn, có sẵn trong repo)
```

Nếu có file nén (ví dụ `hcmut-gps.zip`):

```bash
mkdir -p data/raw/data
unzip -o hcmut-gps.zip "part1/*" "part2/*" -d data/raw
mv data/raw/part1/part1/*.json data/raw/data/ 2>/dev/null
mv data/raw/part2/part2/*.json data/raw/data/ 2>/dev/null
rm -rf data/raw/part1 data/raw/part2
```

### Bước 1 — Khởi động hệ thống (core services)

```bash
docker compose up --build -d
```

Đợi ~1–2 phút để services healthy.

| Service | URL / port | Mô tả |
|---------|------------|--------|
| Zookeeper | localhost:2181 | Điều phối Kafka |
| Kafka | localhost:29092 | Message broker |
| Elasticsearch | http://localhost:9200 | Storage & search |
| Kibana | http://localhost:5601 | Giao diện dashboard |
| Logstash | (internal) | Kafka → ES pipeline |

### Bước 2 — Tạo index ES & saved objects Kibana

Chạy **từ thư mục gốc repo**:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r scripts/requirements.txt

python scripts/create_index.py      # tạo index bus_waypoints + mapping geo_point
python scripts/setup_kibana.py      # Data View + Dashboard + visualizations
python scripts/setup_kibana_map.py  # Map saved object (live map + heatmap)
```

> Cần Elasticsearch và Kibana đang chạy (Bước 1). Chỉ cần chạy **một lần**.

### Bước 3 — Chạy Simulator (giả lập → Kafka)

```bash
# Chạy nền
docker compose --profile simulate up simulator --build -d

# Hoặc chạy foreground xem log trực tiếp
docker compose --profile simulate up simulator --build
```

Simulator sẽ:
- Đọc `data/raw/data/*.json` và enrich tuyến xe
- Shift timestamp về "bây giờ" để Kibana hiển thị như real-time
- Gửi theo batch vào Kafka topic `bus-gps-raw` (mặc định 50 bản ghi/batch, cách nhau 200ms)
- Logstash tự động consume và đẩy vào Elasticsearch

### Bước 4 — Xem Dashboard trên Kibana

Truy cập http://localhost:5601

| Đường dẫn | Nội dung |
|-----------|----------|
| `/app/dashboards#/view/smart-bus-dashboard` | Dashboard tổng hợp |
| `/app/maps/map/smart-bus-live-map` | Bản đồ GPS live + heatmap |

Kiểm tra dữ liệu đang vào ES:

```bash
curl -s http://localhost:9200/bus_waypoints/_count
```

`count > 0` → chuỗi Simulator → Kafka → Logstash → ES đang chạy.

## Kiểm tra từng chặng

```bash
# Simulator đang phát không?
docker logs -f smart-bus-simulator

# Logstash đang consume Kafka và đẩy ES?
docker logs -f smart-bus-logstash

# ES có dữ liệu chưa?
curl -s http://localhost:9200/bus_waypoints/_count
```

## Cấu hình Simulator

| Variable | Default | Mô tả |
|----------|---------|--------|
| `DATA_MODE` | `json` | `json` = đọc `data/raw/data/*.json` |
| `BATCH_SIZE` | `50` | Số records mỗi batch |
| `DELAY_MS` | `200` | Khoảng cách giữa các batch (ms) |
| `SPEED_MULTIPLIER` | `1.0` | Hệ số tốc độ phát (2.0 = nhanh gấp đôi) |
| `LOOP` | `false` | Lặp lại khi hết dữ liệu |
| `MAX_FILES` | `0` | Giới hạn số file JSON (0 = tất cả) |

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

## Cấu trúc thư mục

```
├── data/
│   ├── raw/
│   │   ├── data/                     ← sub_raw_*.json — simulator đọc từ đây
│   │   ├── vehicle_route_mapping.json
│   │   └── routes_clean.json
│   └── processed/                    ← (không dùng trong pipeline JSON)
│
├── scripts/
│   ├── create_index.py               ← tạo ES index với geo_point mapping
│   ├── setup_kibana.py               ← Data View + Dashboard + visualizations
│   ├── setup_kibana_map.py           ← Kibana Maps saved object
│   └── requirements.txt
│
├── simulator/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── simulate_gps.py               ← Kafka producer
│
├── logstash/
│   ├── config/logstash.yml
│   └── pipeline/kafka-to-es.conf     ← ETL: Kafka → parse → ES
│
├── kibana/kibana.yml
└── docker-compose.yml
```

## Xử lý dữ liệu ở đâu?

| Giai đoạn | Thành phần | Việc làm |
|-----------|------------|----------|
| Phát dữ liệu | `simulator/simulate_gps.py` | Đọc JSON, enrich tuyến, shift thời gian → Kafka |
| Hàng đợi | Kafka | Buffer |
| ETL | `logstash/pipeline/kafka-to-es.conf` | Parse JSON, `@timestamp`, `geo_point` → ES |
| Lưu & search | Elasticsearch | Index, lưu trữ |
| Hiển thị | Kibana | Query ES, vẽ chart/map |

## Lưu ý khi demo

- Timestamp được shift về "bây giờ" → biểu đồ trông như real-time
- Dashboard Kibana auto-refresh theo cấu hình đã tạo (vài giây)
- Tăng `SPEED_MULTIPLIER` hoặc giảm `DELAY_MS` để demo nhanh hơn
- Base map dùng OpenStreetMap — không cần Elastic Maps Service
