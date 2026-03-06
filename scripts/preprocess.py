from pathlib import Path

import pandas as pd


RAW_PATH = Path("data/raw/bus_gps.csv")
PROCESSED_PATH = Path("data/processed/bus_gps_clean.csv")


def main() -> None:
    if not RAW_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file raw CSV tại {RAW_PATH}. "
            "Hãy tải dataset về và lưu đúng đường dẫn."
        )

    df = pd.read_csv(RAW_PATH)

    # Skeleton cleaning – tùy dataset thực tế mà chỉnh thêm.
    required_cols = {"vehicle", "datetime", "x", "y"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"Thiếu các cột bắt buộc trong CSV: {', '.join(sorted(missing))}"
        )

    df = df.dropna(subset=["vehicle", "datetime", "x", "y"])
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime"])

    PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_PATH, index=False)
    print(f"Đã lưu dữ liệu đã làm sạch tại {PROCESSED_PATH}")


if __name__ == "__main__":
    main()

