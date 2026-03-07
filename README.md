## Smart Bus Search

Hệ thống search + analytics cho dữ liệu GPS xe buýt, dùng **Elasticsearch** cho geo search, **FastAPI** cho backend và **Streamlit** cho UI.

### Kiến trúc tổng quan

- **data**: chứa raw CSV từ Kaggle và dữ liệu đã làm sạch.
- **scripts**: script Python để:
  - tiền xử lý CSV (`preprocess.py`)
  - tạo index Elasticsearch (`create_index.py`)
  - ingest dữ liệu (`ingest_bus_gps.py`)
- **backend**: API FastAPI:
  - `/api/search/*`: tìm xe gần vị trí, hành trình xe, real‑time vehicles
  - `/api/analytics/*`: geo grid density, thống kê hoạt động
- **ui**: ứng dụng Streamlit gọi backend và hiển thị map + bảng.

### Chuẩn bị môi trường

1. Cài Docker + Docker Compose.
2. Tạo file `.env` ở thư mục gốc (đã có sẵn template, chỉnh nếu cần):

```bash
ES_HOST=http://elasticsearch:9200
ES_INDEX=bus_waypoints
ES_USER=
ES_PASSWORD=
BACKEND_URL=http://localhost:8000
```

### Chạy bằng Docker Compose

```bash
docker compose up --build
```

- Elasticsearch: `http://localhost:9200`
- FastAPI: `http://localhost:8000/docs`
- Streamlit: `http://localhost:8501`

Để dừng:

```bash
docker compose down
```

### Hướng dẫn nhanh cho member trong team

#### Setup lần đầu

1. **Clone repo về máy**:
   ```bash
   git clone <repo-url>
   cd smart-bus-search
   ```

2. **Đảm bảo đã cài Docker Desktop**.

3. **Chuẩn bị Kaggle API** (nếu cần download dữ liệu):
   - Tải `kaggle.json` từ https://www.kaggle.com/settings/account
   - Copy vào thư mục gốc project: `./kaggle.json`

4. **Chạy setup one-shot**:
   ```bash
   ./scripts/setup.sh
   ```

   Hoặc chạy từng bước:
   ```bash
   docker compose up -d elasticsearch backend
   ./scripts/load_kaggle_to_es.sh
   ```

5. **Kiểm tra các service**:
   - FastAPI docs: `http://localhost:8000/docs`
   - Elasticsearch: `http://localhost:9200/_cat/indices`
   - Streamlit UI: `http://localhost:8501` (nếu chạy cả service)

#### Phát triển hàng ngày

- **Không cần cài Python, Elasticsearch… trên máy** – tất cả đã nằm trong container.
- Khi code backend:
  - Sửa code trong `backend/app/**`
  - Docker sẽ auto-reload (hoặc restart container nếu cần)
- Khi code UI:
  - Sửa code trong `ui/**`, Streamlit sẽ tự reload.
- **Chạy test**:
  ```bash
  docker compose exec backend pytest tests/
  ```
- **Dừng service**:
  ```bash
  docker compose down
  ```

### Quy trình dữ liệu

#### Option 1: Sample data (~214k records, đủ để demo/test)

Mặc định script `load_kaggle_to_es.sh` đã tải và xử lý `sample.json` (~214k waypoints).

```bash
./scripts/load_kaggle_to_es.sh
```

Hoặc chạy từng bước:

```bash
# 1. Dataset đã có sample.json trong data/raw/
# 2. Preprocess
python scripts/preprocess.py

# 3. Tạo index ES
python scripts/create_index.py

# 4. Ingest vào ES
python scripts/ingest_bus_gps.py
```

#### Option 2: Full dataset (~518 files, hàng triệu records)

⚠️ **Lưu ý**: Xử lý full dataset rất tốn thời gian (10-30 phút) và tài nguyên.

Dataset split thành 2 thư mục:
- `data/raw/part1/part1/sub_raw_100.json` → `sub_raw_433.json` (334 files)
- `data/raw/part2/part2/sub_raw_434.json` → `sub_raw_618.json` (184 files)

Script `preprocess.py` tự động tìm tất cả JSON files bằng glob pattern:

```python
# Trong preprocess.py
json_files = sorted(glob.glob("data/raw/part*/part*/*.json")) + \
             sorted(glob.glob("data/raw/*.json"))
```

Để process full dataset:

```bash
# 1. Đảm bảo đã có đủ part1, part2
ls data/raw/part1/part1/*.json | wc -l  # should be 334
ls data/raw/part2/part2/*.json | wc -l  # should be 184

# 2. Chạy preprocessing (chờ 10-30 phút)
python scripts/preprocess.py  # or via Docker

# 3. Xóa index cũ và tạo lại
curl -X DELETE http://localhost:9200/bus_waypoints
python scripts/create_index.py

# 4. Ingest (có thể mất 30+ phút)
python scripts/ingest_bus_gps.py
```

**Khuyến nghị**: Dùng sample data cho development, chỉ load full dataset khi cần testing với data thật hoặc production.

### Các use case chính

- Tìm xe buýt trong bán kính 500m–2km quanh vị trí người dùng (geo_distance).
- Tìm xe đang hoạt động trong 5 phút gần nhất (filter theo timestamp).
- Theo dõi hành trình 1 xe trong 1 giờ gần đây.
- Aggregation theo geo grid để phân tích mật độ hoạt động.
- Lọc theo `vehicle`, `ignition`, `heading`, `aircon`, `door_up`, `door_down`.

