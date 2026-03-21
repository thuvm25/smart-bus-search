# Smart Bus GPS Search Engine

Hệ thống search engine cho dữ liệu GPS xe buýt TP.HCM, sử dụng **Elasticsearch** cho geospatial search, **FastAPI** cho backend API, và **Streamlit** cho visualization.

## Kiến trúc tổng quan

```
Elasticsearch 8.15     ← lưu trữ + search engine
      ↑
FastAPI backend        ← REST API (search / analytics / ingest)
      ↑            ↑
Streamlit UI      GPS Simulator
(visualization)   (giả lập real-time GPS)
```

## Yêu cầu

- **Docker Desktop** (bao gồm Docker Compose)
- Không cần cài Python, Elasticsearch hay bất kỳ thứ gì khác trên máy

## Hướng dẫn nhanh cho member

**Bản chi tiết hơn (hai cách tải data, xử lý lỗi, Kaggle):** xem [docs/HUONG_DAN.md](docs/HUONG_DAN.md).

### Bước 1 — Clone repo

```bash
git clone <repo-url>
cd smart-bus-search
```

### Bước 2 — Tải dataset

Tải dataset bus GPS từ [https://sharefile.hpcc.vn/share/NfpoCRX0](https://sharefile.hpcc.vn/share/NfpoCRX0) và giải nén vào `data/raw/`.

### Bước 3 — Chạy hệ thống

```bash
docker compose up --build
```

Đợi khoảng 30-60 giây để Elasticsearch khởi động xong. Khi thấy log `Uvicorn running on ...` là đã sẵn sàng.

| Service        | URL                          |
|----------------|------------------------------|
| Elasticsearch  | http://localhost:9200        |
| FastAPI docs   | http://localhost:8000/docs   |
| Streamlit UI   | http://localhost:8501        |

### Bước 4 — Tiền xử lý và nạp dữ liệu

Mở terminal mới (giữ docker compose chạy):

```bash
# Cài dependencies cho scripts
pip install pandas python-dotenv elasticsearch

# Tiền xử lý raw JSON → CSV sạch
python scripts/preprocess.py

# Tạo index Elasticsearch (nếu chưa có)
python scripts/create_index.py

# Nạp dữ liệu vào Elasticsearch
python scripts/ingest_bus_gps.py
```

### Bước 5 — Chạy GPS Simulator (giả lập real-time)

```bash
docker compose --profile simulate up simulator
```

Simulator sẽ đọc CSV đã xử lý và gửi từng batch lên backend API, giả lập như thiết bị GPS thực gửi dữ liệu.

### Dừng hệ thống

```bash
docker compose down
```

Xóa luôn dữ liệu Elasticsearch:

```bash
docker compose down -v
```

## Cấu trúc thư mục

```
├── data/
│   ├── raw/                      # dataset gốc (JSON từ HPCC)
│   └── processed/                # CSV sau preprocessing
│
├── scripts/
│   ├── preprocess.py             # JSON → CSV sạch
│   ├── create_index.py           # tạo ES index với mapping
│   └── ingest_bus_gps.py         # bulk ingest CSV vào ES
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py               # FastAPI entrypoint
│       ├── config.py             # env config
│       ├── dependencies.py       # ES client dependency
│       ├── schemas.py            # Pydantic models
│       ├── routers/
│       │   ├── search.py         # /api/search/*
│       │   ├── analytics.py      # /api/analytics/*
│       │   └── ingest.py         # /api/ingest/*
│       ├── services/
│       │   └── analytics_service.py
│       ├── core/
│       │   ├── route_mapping.py
│       │   └── stop_lookup.py
│       └── models/
│           └── mapping.py        # ES index mapping definition
│
├── simulator/
│   ├── Dockerfile
│   └── simulate_gps.py          # giả lập GPS real-time
│
├── ui/
│   ├── streamlit_app.py          # Streamlit UI chính
│   ├── api_client.py             # gọi backend API
│   └── components/
│       ├── map_view.py
│       ├── filters.py
│       └── table_view.py
│
├── benchmark/
│   └── benchmark.py              # đánh giá hiệu năng ES
│
├── docker-compose.yml
└── .env
```

## API Endpoints

### Search

| Method | Endpoint              | Mô tả                                       |
|--------|-----------------------|----------------------------------------------|
| GET    | `/api/search/nearby`  | Tìm xe buýt trong bán kính quanh tọa độ     |
| POST   | `/api/search/nearby`  | Giống trên, nhận JSON body                   |
| POST   | `/api/search/active`  | Xe buýt đang hoạt động trong N phút gần nhất |
| POST   | `/api/search/vehicle-trace` | Hành trình GPS của 1 xe cụ thể         |

### Analytics

| Method | Endpoint                    | Mô tả                                     |
|--------|-----------------------------|--------------------------------------------|
| GET    | `/api/analytics/density`    | Mật độ xe theo geohash grid (heatmap)      |
| GET    | `/api/analytics/active-count` | Đếm xe đang hoạt động                  |
| GET    | `/api/analytics/speed`      | Thống kê tốc độ (min/avg/max/histogram)    |
| GET    | `/api/analytics/stats`      | Thông tin index (doc count, size, ...)     |

### Ingest (cho simulator)

| Method | Endpoint              | Mô tả                        |
|--------|-----------------------|-------------------------------|
| POST   | `/api/ingest/waypoint`| Nạp 1 GPS record             |
| POST   | `/api/ingest/batch`   | Nạp batch nhiều records       |

## GPS Simulator

Simulator đọc dữ liệu tĩnh từ CSV và gửi lên backend qua API, giả lập thiết bị GPS IoT:

- Đọc CSV tuần tự theo thời gian
- Shift timestamp về "now" để dữ liệu giống real-time
- Gửi batch 200 records mỗi 2 giây (cấu hình được)
- Backend lưu vào Elasticsearch

Cấu hình qua environment variables:

| Variable       | Default | Mô tả                          |
|----------------|---------|---------------------------------|
| `BATCH_SIZE`   | 200     | Số records mỗi batch           |
| `SEND_INTERVAL`| 2       | Giây giữa các batch            |
| `LOOP`         | false   | Lặp lại khi hết dữ liệu       |

## Benchmark (đánh giá hiệu năng)

```bash
pip install -r benchmark/requirements.txt
python benchmark/benchmark.py --es-host http://localhost:9200
```

Đo lường:

1. **Indexing throughput** — documents/second khi bulk insert
2. **Search latency** — thời gian trả về geo_distance query (min/avg/p95/max)
3. **Aggregation latency** — thời gian chạy geohash_grid aggregation
4. **Scalability** — hiệu năng thay đổi khi tăng data volume (1k → 50k docs)

## Chạy không dùng Docker (backup)

Nếu Docker không chạy được:

```bash
# 1. Cài Elasticsearch local
brew install elasticsearch   # hoặc tải từ elastic.co

# 2. Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. UI
cd ui
pip install -r requirements.txt
streamlit run streamlit_app.py
```
