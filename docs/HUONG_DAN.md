# Hướng dẫn  

Tài liệu này giúp bạn **cài đặt, nạp dữ liệu và chạy** dự án Smart Bus GPS Search từ đầu, không cần đã quen codebase.

## Bạn sẽ làm được gì

- Chạy **Elasticsearch**, **FastAPI** và **Streamlit** bằng Docker.
- Đưa dữ liệu GPS vào Elasticsearch (một trong hai cách: tải tay hoặc Kaggle).
- Mở giao diện web để tìm kiếm / xem analytics.

## Chuẩn bị

| Thứ cần có | Ghi chú |
|------------|---------|
| **Docker Desktop** | Bật Docker, đợi daemon chạy ổn định. |
| **Git** | Clone repo về máy. |
| **(Tuỳ chọn) Tài khoản Kaggle** | Chỉ cần nếu bạn dùng cách tải dataset qua API. |

Sao chép môi trường cấu hình:

```bash
cp .env.example .env
```

File `.env` dùng cho script chạy **trên máy host** (khi gọi `localhost:9200`). Các service trong Docker đã được `docker-compose.yml` gán biến môi trường riêng — bạn ít khi phải sửa thêm.

---

## Luồng dữ liệu (tóm tắt)

1. **Nguồn**: file JSON (dataset GPS) nằm trong `data/raw/`.
2. **Tiền xử lý**: `scripts/preprocess.py` → tạo `data/processed/bus_gps_clean.csv`.
3. **Index**: `scripts/create_index.py` tạo mapping index Elasticsearch.
4. **Nạp**: `scripts/ingest_bus_gps.py` đẩy CSV vào index (mặc định `bus_waypoints`).
5. **Ứng dụng**: UI gọi API → backend truy vấn Elasticsearch.

Bạn chỉ cần hoàn thành bước 1–4 **một lần** (hoặc khi đổi dataset).

---

## Cách 1 — Tải dataset từ Sharefile (theo README chính)

Phù hợp khi nhóm chia sẻ file qua link nội bộ.

### Bước 1: Clone repo

```bash
git clone <repo-url>
cd smart-bus-search
cp .env.example .env
```

### Bước 2: Đặt dữ liệu thô vào `data/raw/`

1. Tải dataset từ link nhóm cung cấp (ví dụ trong README: sharefile HPCC).
2. Giải nén sao cho có **file JSON** đúng cấu trúc mà `preprocess.py` đọc được:
   - Mặc định nhanh: đặt `data/raw/sample.json` (khoảng ~214k bản ghi), **hoặc**
   - Full dataset: các file dưới dạng `data/raw/part*/part*/*.json`.

Nếu thư mục `data/raw/` trống, hãy giữ file `.gitkeep` (đã có trong repo) — không cần commit dữ liệu lên Git.

### Bước 3: Chạy toàn bộ stack

```bash
docker compose up --build
```

Đợi Elasticsearch healthy (khoảng 30–60 giây), backend báo Uvicorn chạy.

| Dịch vụ | URL |
|---------|-----|
| Elasticsearch | http://localhost:9200 |
| API (Swagger) | http://localhost:8000/docs |
| Streamlit UI | http://localhost:8501 |

### Bước 4: Tiền xử lý và nạp vào Elasticsearch

Mở **terminal mới** (giữ `docker compose` đang chạy):

```bash
pip install pandas python-dotenv "elasticsearch>=8.0,<9.0"

# Mặc định: sample.json. Full data:
# PROCESS_FULL_DATASET=true python scripts/preprocess.py

python scripts/preprocess.py
python scripts/create_index.py
python scripts/ingest_bus_gps.py
```

`create_index.py` và `ingest_bus_gps.py` dùng `ES_HOST` trong `.env` — với stack chuẩn phải là `http://localhost:9200`.

### Kiểm tra nhanh

```bash
curl -s http://localhost:9200/bus_waypoints/_count
```

Trả về JSON có `"count"` > 0 là đã có dữ liệu.

---

## Cách 2 — Tải từ Kaggle + script tự động

Phù hợp khi dataset được publish trên Kaggle (trong repo có script trỏ tới dataset `thuvm2502/hcmut-gps`).

### Bước 1: Lấy API key Kaggle

1. Vào [Kaggle → Account → API](https://www.kaggle.com/settings/account).
2. Tạo / tải file `kaggle.json`.
3. Đặt file **ở thư mục gốc repo**: `smart-bus-search/kaggle.json`.

**Quan trọng:** Không commit `kaggle.json` lên Git (chứa username/key). File này đã được liệt kê trong `.gitignore` của repo.

### Bước 2: Chạy script nạp dữ liệu

```bash
chmod +x scripts/load_kaggle_to_es.sh
./scripts/load_kaggle_to_es.sh
```

Script sẽ:

- Bật container **Elasticsearch** (`docker compose up -d elasticsearch`).
- Chạy container Python tạm: cài `kaggle`, tải dataset, giải nén vào `data/raw/`, chạy `preprocess.py`, `create_index.py`, `ingest_bus_gps.py`.
- Kết nối ES trên máy host qua `http://host.docker.internal:9200` (macOS / Windows Docker Desktop).

### Bước 3: Chạy backend + UI

```bash
docker compose up --build
```

Nếu bạn chỉ cần API trước, có thể dùng `./scripts/setup.sh` (tương tác: có/không `kaggle.json`) — script đó bật `elasticsearch` + `backend` và gọi `load_kaggle_to_es.sh` khi có key.

### Linux (Docker Engine, không dùng Docker Desktop)

`host.docker.internal` đôi khi **chưa** có sẵn. Nếu `load_kaggle_to_es.sh` báo không kết nối được ES:

- Thêm `extra_hosts` cho service cần thiết trong `docker-compose.yml`, **hoặc**
- Chạy preprocess / create_index / ingest **trực tiếp trên host** như **Cách 1, bước 4** (sau khi đã tải dữ liệu vào `data/raw/` bằng tay hoặc sửa script cho phù hợp môi trường của bạn).

---

## (Tuỳ chọn) Giả lập GPS real-time

Sau khi đã có `data/processed/bus_gps_clean.csv`:

```bash
docker compose --profile simulate up simulator
```

Simulator đọc CSV và POST batch lên API, giống thiết bị gửi điểm GPS.

---

## Xử lý sự cố thường gặp

| Hiện tượng | Hướng xử lý |
|------------|-------------|
| `FileNotFoundError` khi chạy `preprocess.py` | Kiểm tra `data/raw/` có `sample.json` hoặc đủ thư mục `part*/part*/*.json`. |
| `ingest_bus_gps.py` không tìm thấy CSV | Chạy lại `preprocess.py` thành công trước. |
| UI trống / API lỗi | Xác nhận `docker compose` chạy, ES có doc: `curl .../_count`. |
| Kaggle: `403` / unauthorized | Kiểm tra `kaggle.json`, chấp nhận điều khoản dataset trên trang Kaggle. |
| Port 9200 / 8000 / 8501 bị chiếm | Tắt process khác hoặc đổi map port trong `docker-compose.yml`. |

---

## Tài liệu thêm

- **README gốc** (API, cấu trúc thư mục, benchmark): [`../README.md`](../README.md)
- **Swagger**: http://localhost:8000/docs (khi backend đang chạy)

Nếu bạn cập nhật dataset hoặc index mapping, nên thống nhất với nhóm và ghi chú trong PR / wiki nhóm để người sau không bị lệch phiên bản dữ liệu.
