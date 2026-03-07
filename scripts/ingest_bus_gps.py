import os
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch, helpers
import pandas as pd


PROCESSED_PATH = Path("data/processed/bus_gps_clean.csv")


def main() -> None:
    load_dotenv()
    es_host = os.getenv("ES_HOST", "http://localhost:9200")
    es_index = os.getenv("ES_INDEX", "bus_waypoints")

    if not PROCESSED_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file processed CSV tại {PROCESSED_PATH}. "
            "Hãy chạy scripts/preprocess.py trước."
        )

    df = pd.read_csv(PROCESSED_PATH)
    if not {"x", "y"}.issubset(df.columns):
        raise ValueError("CSV cần có cột 'x' (lon) và 'y' (lat).")

    # Create Elasticsearch client with compatible API version
    es = Elasticsearch(
        es_host,
        request_timeout=30,
        headers={"Accept": "application/json", "Content-Type": "application/json"}
    )

    def _iter_docs():
        for row in df.itertuples(index=False):
            doc = row._asdict()
            lon = doc.pop("x")
            lat = doc.pop("y")
            doc["location"] = {"lon": float(lon), "lat": float(lat)}

            # Convert NaN/None values to None for JSON serialization
            cleaned_doc = {}
            for key, val in doc.items():
                # Skip NaN and None values (Elasticsearch will use defaults)
                if pd.isna(val):
                    cleaned_doc[key] = None
                else:
                    cleaned_doc[key] = val

            yield {"_index": es_index, "_source": cleaned_doc}

    try:
        success_count = 0
        error_count = 0
        for ok, action in helpers.streaming_bulk(
            es, _iter_docs(), chunk_size=500,
            raise_on_error=False
        ):
            if ok:
                success_count += 1
            else:
                error_count += 1
                if error_count <= 3:  # Print first 3 errors only
                    print(f"Document ingest error: {action}")

        if error_count > 0:
            print(f"✓ Ingest xong: {success_count} thành công, {error_count} lỗi")
        else:
            print(f"✓ Đã ingest {len(df)} documents vào index '{es_index}'.")
    except Exception as e:
        print(f"⚠️ Ingest lỗi: {e}")
        raise


if __name__ == "__main__":
    main()

