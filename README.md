# Smart Bus GPS Search

Hệ thống giả lập streaming dữ liệu GPS xe buýt TP.HCM qua pipeline đầy đủ từ nguồn đến giao diện:

```
Data (JSON) → Simulator → Kafka → Logstash → Elasticsearch → FastAPI → Streamlit UI
                                                                  └──────→ Kibana
```

Dữ liệu gốc là dữ liệu lịch sử (~104 triệu bản ghi GPS), được giả lập thành luồng dữ liệu thời gian thực và hiển thị trên 2 lớp giao diện: Kibana (phân tích) và Streamlit (bảng điều khiển tùy chỉnh).

## Kiến trúc

```
┌───────────┐    ┌─────────┐    ┌──────────┐    ┌───────────────┐
│ Simulator │───▶│  Kafka  │───▶│ Logstash │───▶│ Elasticsearch │
│(Producer) │    │(Broker) │    │  (ETL)   │    │  (Storage)    │
└───────────┘    └─────────┘    └──────────┘    └───────┬───────┘
  Đọc JSON,        Bộ đệm        Phân tích JSON,         │
  làm giàu dữ liệu topic:        geo_point,              ├──────▶ Kibana :5601
  tuyến đường,     bus-gps-raw   @timestamp              │        Dashboard + Maps
  dịch chuyển                    → index ES              │
  thời gian                                              └──────▶ FastAPI :8000
  → gửi Kafka                                                     /api/livebus
                                                                  /api/fuzzysearch
                                                                       │
                                                                       ▼
                                                                  Streamlit :8501
                                                                  Bản đồ trực tiếp + Tìm kiếm tuyến
```

## Yêu cầu hệ thống

- **Docker Desktop** ≥ 4.x (cấp ít nhất **6 GB RAM** trong phần cài đặt Docker Desktop)
- **Python 3.9+** (chỉ cần để chạy Kibana setup scripts)

---

## Hướng dẫn cài đặt

### Bước 0 — Clone dự án & chuẩn bị dữ liệu

```bash
git clone <repo-url>
cd smart-bus-search
```

Đặt các file dữ liệu GPS JSON vào đúng cấu trúc thư mục sau:

```
data/raw/
├── data/                          ← đặt các file sub_raw_*.json vào đây
│   ├── sub_raw_1.json
│   └── ...
├── vehicle_route_mapping.json     ← có sẵn trong kho lưu trữ
└── routes_clean.json              ← có sẵn trong kho lưu trữ
```

Nếu bạn có file nén `hcmut-gps.zip`:

```bash
mkdir -p data/raw/data
unzip -o hcmut-gps.zip "part1/*" "part2/*" -d data/raw
mv data/raw/part1/part1/*.json data/raw/data/ 2>/dev/null
mv data/raw/part2/part2/*.json data/raw/data/ 2>/dev/null
rm -rf data/raw/part1 data/raw/part2
```

### Bước 1 — Khởi động toàn bộ hệ thống

```bash
docker compose --profile simulate up -d --build
```

Docker sẽ tự động khởi động các dịch vụ theo đúng thứ tự:

1. Elasticsearch & Kafka khởi động và chờ đến khi `healthy`
2. **`init-index`** chạy `create_index.py` — tạo index `bus_waypoints` với mapping chính xác (`geo_point`, `keyword`, v.v.)
3. Logstash bắt đầu sau khi index đã sẵn sàng — tránh xung đột Dynamic Mapping
4. Backend, UI, Simulator khởi động song song

Đợi khoảng 1–2 phút để tất cả các dịch vụ ở trạng thái sẵn sàng.

### Bước 2 — (Tùy chọn) Thiết lập Kibana Dashboard & Maps

Chạy **một lần duy nhất** nếu bạn muốn sử dụng Kibana:

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scripts/setup_kibana.py      # Tạo Data View + Dashboard + các biểu đồ
python scripts/setup_kibana_map.py  # Thiết lập Kibana Maps (bản đồ trực tiếp + heatmap)
```

### Bước 3 — Truy cập các địa chỉ

| Địa chỉ | Nội dung |
|---------|----------|
| http://localhost:8501 | Streamlit — Bản đồ trực tiếp + Tìm kiếm tuyến xe |
| http://localhost:8000/docs | FastAPI — Swagger UI |
| http://localhost:5601/app/dashboards#/view/smart-bus-dashboard | Kibana Dashboard |
| http://localhost:5601/app/maps/map/smart-bus-live-map | Kibana Maps trực tiếp |

---

## Kiểm tra từng công đoạn

```bash
# ES có dữ liệu chưa?
curl -s http://localhost:9200/bus_waypoints/_count

# Backend API có hoạt động không?
curl -s http://localhost:8000/health

# Simulator có đang phát dữ liệu không?
docker logs -f smart-bus-simulator

# Logstash có đang nhận và đẩy dữ liệu vào ES không?
docker logs -f smart-bus-logstash
```

---

## Cấu hình Simulator

Simulator đọc cấu hình từ file `.env` ở thư mục gốc:

| Biến môi trường | Mặc định | Mô tả |
|----------------|---------|-------|
| `BATCH_SIZE` | `50` | Số lượng bản ghi gửi tới Kafka mỗi đợt |
| `DELAY_MS` | `200` | Khoảng thời gian giữa các đợt gửi (ms) |
| `SPEED_MULTIPLIER` | `1.0` | Hệ số tốc độ phát (2.0 = nhanh gấp đôi) |
| `LOOP` | `false` | Tự động lặp lại từ đầu khi hết dữ liệu |
| `MAX_FILES` | `0` | Giới hạn số file JSON xử lý (0 = tất cả) |

Tạm dừng / Tiếp tục luồng dữ liệu:

```bash
docker kill --signal=SIGUSR1 smart-bus-simulator
```

---

## Khởi động & Dừng hệ thống

### Dừng (giữ lại dữ liệu trong ES)

```bash
docker compose --profile simulate down
```

Lần tiếp theo `docker compose up` sẽ hoạt động ngay, không cần setup lại.

### Làm mới hoàn toàn (xóa sạch dữ liệu ES)

```bash
# 1. Xóa tất cả container và volume
docker compose --profile simulate down -v

# 2. Khởi động lại (init-index sẽ tự tạo lại index với mapping đúng)
docker compose --profile simulate up -d --build
```

---

## Phát triển — Chỉnh sửa code không cần khởi động lại Docker

- **Backend** (`backend/`): uvicorn chạy với `--reload`, tự động tải lại khi lưu file.
- **UI** (`ui/`): Streamlit chạy với `--server.runOnSave true`, tự động tải lại trang.
- Chỉ cần `--build` lại khi thêm thư viện mới vào `requirements.txt`.

---

## Cấu trúc thư mục

```
├── backend/                          ← FastAPI REST API
│   ├── Dockerfile
│   └── app/
│       ├── main.py                   ← Điểm đầu vào, CORS, health check
│       ├── core/es_client.py         ← Elasticsearch client (singleton)
│       └── routers/
│           ├── livebus.py            ← GET /api/livebus (vị trí dạng GeoJSON)
│           └── fuzzysearch.py        ← GET /api/fuzzysearch (tìm kiếm tuyến)
│
├── ui/
│   ├── Dockerfile
│   └── smartsearchbus_web.py         ← Giao diện Streamlit
│
├── simulator/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── simulate_gps.py               ← Kafka producer
│
├── logstash/
│   ├── config/logstash.yml
│   └── pipeline/kafka-to-es.conf     ← ETL: Kafka → xử lý → Elasticsearch
│
├── scripts/
│   ├── create_index.py               ← Tạo index ES với mapping geo_point (chạy tự động qua Docker)
│   ├── setup_kibana.py               ← Thiết lập Data View, Dashboard & Biểu đồ (chạy tay 1 lần)
│   └── setup_kibana_map.py           ← Thiết lập Kibana Maps (chạy tay 1 lần)
│
├── kibana/kibana.yml
├── data/
│   └── raw/
│       ├── data/                     ← sub_raw_*.json (dữ liệu nguồn)
│       ├── vehicle_route_mapping.json
│       └── routes_clean.json
│
├── .env                              ← Cấu hình Simulator
├── requirements.txt                  ← Thư viện cho backend, UI và scripts
└── docker-compose.yml
```

## Lưu ý khi demo

- Timestamp được dịch chuyển về "hiện tại" → biểu đồ Kibana và bản đồ Streamlit hiển thị như dữ liệu thời gian thực.
- Tăng `SPEED_MULTIPLIER` hoặc giảm `DELAY_MS` trong `.env` để dữ liệu phát nhanh hơn.
- Bản đồ nền dùng OpenStreetMap — không yêu cầu bản quyền Elastic Maps Service.
