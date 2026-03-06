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

- **Bước 1**: Clone repo về máy.
- **Bước 2**: Đảm bảo đã cài Docker Desktop.
- **Bước 3**: Ở thư mục project, chạy:

  ```bash
  docker compose up --build
  ```

- **Không cần cài Python, Elasticsearch… trên máy** – tất cả đã nằm trong container.
- Khi code backend:
  - Sửa code trong `backend/app/**`
  - Docker sẽ rebuild khi bạn `up --build` lại.
- Khi code UI:
  - Sửa code trong `ui/**`, Streamlit sẽ tự reload (hoặc restart container UI nếu cần).

### Quy trình dữ liệu

1. Tải dataset bus GPS từ nguồn (Kaggle / link HPCC) về `data/raw/bus_gps.csv`.
2. Chạy preprocessing:

```bash
python scripts/preprocess.py
```

3. Tạo index Elasticsearch:

```bash
python scripts/create_index.py
```

4. Ingest dữ liệu đã làm sạch:

```bash
python scripts/ingest_bus_gps.py
```

### Các use case chính

- Tìm xe buýt trong bán kính 500m–2km quanh vị trí người dùng (geo_distance).
- Tìm xe đang hoạt động trong 5 phút gần nhất (filter theo timestamp).
- Theo dõi hành trình 1 xe trong 1 giờ gần đây.
- Aggregation theo geo grid để phân tích mật độ hoạt động.
- Lọc theo `vehicle`, `ignition`, `heading`, `aircon`, `door_up`, `door_down`.

