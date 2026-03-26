# Smart Bus GPS — Real-time Streaming Pipeline

Hệ thống giả lập streaming dữ liệu GPS xe buýt TP.HCM qua pipeline:

```
Data (CSV) → Simulator → Kafka → Logstash → Elasticsearch → Kibana
```

Dữ liệu gốc là historical data, được simulate thành real-time streaming để demo hệ thống.

## Kiến trúc

```
┌─────────────┐     ┌─────────┐     ┌───────────┐     ┌───────────────┐     ┌────────┐
│  Simulator   │────▶│  Kafka  │────▶│ Logstash  │────▶│ Elasticsearch │────▶│ Kibana │
│ (Producer)   │     │ (Broker)│     │  (ETL)    │     │  (Storage)    │     │ (Viz)  │
└─────────────┘     └─────────┘     └───────────┘     └───────────────┘     └────────┘
  Đọc CSV,            Buffer          Parse JSON,       Lưu trữ &           Dashboard
  shift timestamp,    messages        transform,        index data           realtime
  gửi từng batch                      đẩy vào ES
```

## Yêu cầu

- **Docker Desktop** (bao gồm Docker Compose)
- RAM tối thiểu: **6 GB** (cho Kafka + ES + Logstash + Kibana)
- Không cần cài thêm gì khác

## Hướng dẫn nhanh

### Bước 1 — Clone & chuẩn bị data

```bash
git clone <repo-url>
cd smart-bus-search
```

Tải dataset từ [HPCC](https://sharefile.hpcc.vn/share/NfpoCRX0) và giải nén vào `data/raw/`.

### Bước 2 — Tiền xử lý dữ liệu

```bash
pip install pandas
python scripts/preprocess.py
```

Kết quả: `data/processed/bus_gps_clean.csv` (~214k records)

### Bước 3 — Khởi động hệ thống

```bash
docker compose up --build -d
```

Đợi 1-2 phút để tất cả services khởi động.

| Service        | URL                    | Mô tả                      |
|----------------|------------------------|-----------------------------|
| Kafka          | localhost:29092        | Message broker              |
| Elasticsearch  | http://localhost:9200  | Storage & search engine     |
| Kibana         | http://localhost:5601  | Dashboard & visualization   |
| Logstash       | (internal)             | Kafka → ES pipeline         |

### Bước 4 — Tạo ES index (lần đầu)

```bash
pip install python-dotenv elasticsearch
python scripts/create_index.py
```

### Bước 5 — Chạy Simulator (giả lập real-time)

```bash
docker compose --profile simulate up simulator --build
```

Simulator sẽ:
- Đọc CSV theo thứ tự timestamp
- Shift timestamp về "now" (dữ liệu cũ hiển thị như mới)
- Gửi từng batch vào Kafka topic `bus-gps-raw`
- Logstash tự động consume và đẩy vào Elasticsearch
- Kibana hiển thị data update liên tục

### Bước 6 — Mở Kibana Dashboard

1. Truy cập http://localhost:5601
2. Vào **Management → Stack Management → Data Views**
3. Tạo Data View mới: pattern = `bus_waypoints`, time field = `@timestamp`
4. Vào **Discover** để xem data streaming vào
5. Vào **Dashboard** để tạo visualizations

## Cấu hình Simulator

| Variable            | Default         | Mô tả                                 |
|---------------------|-----------------|----------------------------------------|
| `BATCH_SIZE`        | 50              | Số records mỗi batch gửi vào Kafka    |
| `DELAY_MS`          | 200             | Milliseconds giữa các batch           |
| `SPEED_MULTIPLIER`  | 1.0             | Tốc độ phát (2.0 = nhanh gấp đôi)    |
| `LOOP`              | false           | Lặp lại khi hết dữ liệu              |

### Điều khiển khi đang chạy

```bash
# Pause / Resume stream
docker kill --signal=SIGUSR1 smart-bus-simulator

# Tăng tốc: sửa SPEED_MULTIPLIER trong docker-compose.yml rồi restart simulator
```

## Nạp dữ liệu bulk (không qua Kafka)

Nếu muốn nạp toàn bộ data một lần vào ES (bypass pipeline):

```bash
python scripts/ingest_bus_gps.py
```

## Dừng hệ thống

```bash
docker compose --profile simulate down
```

Xóa luôn data ES:

```bash
docker compose --profile simulate down -v
```

## Cấu trúc thư mục

```
├── data/
│   ├── raw/                          # dataset gốc (JSON từ HPCC)
│   └── processed/                    # CSV sau preprocessing
│
├── scripts/
│   ├── preprocess.py                 # JSON → CSV sạch
│   ├── create_index.py               # tạo ES index với mapping
│   └── ingest_bus_gps.py             # bulk ingest CSV vào ES (bypass Kafka)
│
├── simulator/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── simulate_gps.py              # Kafka producer (giả lập GPS real-time)
│
├── logstash/
│   ├── config/
│   │   └── logstash.yml             # Logstash settings
│   └── pipeline/
│       └── kafka-to-es.conf         # Pipeline: Kafka → ES
│
├── docker-compose.yml                # Kafka + ES + Kibana + Logstash + Simulator
├── .env
└── .env.example
```

## Kibana — Gợi ý Dashboard

Sau khi data đã streaming vào, tạo các visualization trong Kibana:

- **Time-series line chart**: số lượng GPS records theo thời gian
- **Map visualization**: vị trí xe buýt trên bản đồ (dùng field `location`)
- **Metric**: tổng số xe đang hoạt động
- **Bar chart**: phân bổ tốc độ (speed histogram)
- **Data table**: top xe buýt theo số records

## Lưu ý khi demo

- Dữ liệu cũ nhưng timestamp được shift về "now" → hiển thị như real-time
- Dashboard Kibana auto-refresh để thấy data update liên tục
- Có thể pause/resume stream bất cứ lúc nào
- Tăng `SPEED_MULTIPLIER` để demo nhanh hơn
