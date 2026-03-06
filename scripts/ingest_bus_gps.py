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

    es = Elasticsearch(es_host)

    def _iter_docs():
        for row in df.itertuples(index=False):
            doc = row._asdict()
            lon = doc.pop("x")
            lat = doc.pop("y")
            doc["location"] = {"lon": float(lon), "lat": float(lat)}
            yield {"_index": es_index, "_source": doc}

    helpers.bulk(es, _iter_docs())
    print(f"Đã ingest {len(df)} documents vào index '{es_index}'.")


if __name__ == "__main__":
    main()

