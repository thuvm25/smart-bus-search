## Smart Bus Search — project rules

### Run (Docker)

- **Core stack (ES + backend + UI)**:

```bash
docker compose up -d --build
```

- **Realtime simulator (GPS stream)**:

```bash
docker compose --profile simulate up -d simulator
```

- **Benchmark (via UI / backend API)**:
  - UI: mở `http://localhost:8501` → tab **⚡ Benchmark**
  - API: `POST /api/benchmark/run`

### Common pitfalls

- **UI/benchmark “Connection refused localhost:9200”**:
  - Trong Docker, `localhost` là **bên trong container**. Luôn chạy benchmark **qua backend** (`/api/benchmark/run`) hoặc trỏ ES host đúng.

- **Không thấy realtime data**:
  - Simulator chỉ chạy khi bật profile `simulate`.
  - Simulator cần file `data/processed/bus_gps_clean.csv` (tạo bởi `scripts/preprocess.py`).
  - UI có panel **Realtime ingest (last 60s)** (gọi `GET /api/analytics/realtime`) để kiểm chứng simulator đang bơm dữ liệu.

### Preprocess (host) with venv (macOS PEP-668 safe)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install pandas python-dotenv
python scripts/preprocess.py
```

