"""
Performance benchmark for Elasticsearch in the Smart Bus GPS system.

Measures:
  1. Indexing throughput   – documents/sec via bulk API
  2. Search latency        – geo_distance query response time
  3. Aggregation latency   – geohash_grid + cardinality
  4. Scalability           – how metrics change as data volume grows

Usage:
  pip install -r requirements.txt
  python benchmark.py [--es-host http://localhost:9200] [--index bus_waypoints]
"""

from __future__ import annotations

import argparse
import random
import statistics
import time
from datetime import datetime, timedelta, timezone

from elasticsearch import Elasticsearch, helpers
from tabulate import tabulate


# ─── synthetic data generator ────────────────────────────────────────

HCM_LAT = (10.70, 10.90)
HCM_LON = (106.60, 106.80)
VEHICLES = [f"vehicle_{i:04d}" for i in range(200)]


def _random_doc() -> dict:
    return {
        "vehicle": random.choice(VEHICLES),
        "datetime": (
            datetime.now(tz=timezone.utc) - timedelta(seconds=random.randint(0, 3600))
        ).isoformat(),
        "location": {
            "lat": random.uniform(*HCM_LAT),
            "lon": random.uniform(*HCM_LON),
        },
        "speed": round(random.uniform(0, 60), 1),
        "ignition": random.choice([True, False]),
    }


# ─── benchmark functions ─────────────────────────────────────────────

def bench_indexing(es: Elasticsearch, index: str, n: int) -> dict:
    """Bulk-index n synthetic documents and measure throughput."""
    docs = [{"_index": index, "_source": _random_doc()} for _ in range(n)]

    t0 = time.perf_counter()
    success, errors = helpers.bulk(es, docs, chunk_size=500, raise_on_error=False)
    elapsed = time.perf_counter() - t0

    es.indices.refresh(index=index)

    return {
        "documents": n,
        "success": success,
        "errors": len(errors) if isinstance(errors, list) else 0,
        "elapsed_sec": round(elapsed, 3),
        "docs_per_sec": round(n / elapsed, 1),
    }


def bench_search_latency(es: Elasticsearch, index: str, runs: int = 50) -> dict:
    """Run geo_distance queries and measure latency distribution."""
    latencies: list[float] = []
    for _ in range(runs):
        lat = random.uniform(*HCM_LAT)
        lon = random.uniform(*HCM_LON)
        radius = random.choice([500, 1000, 2000])

        body = {
            "size": 20,
            "query": {
                "bool": {
                    "filter": [
                        {"geo_distance": {"distance": f"{radius}m", "location": {"lat": lat, "lon": lon}}},
                    ]
                }
            },
        }

        t0 = time.perf_counter()
        es.search(index=index, **body)
        latencies.append((time.perf_counter() - t0) * 1000)

    return {
        "runs": runs,
        "min_ms": round(min(latencies), 2),
        "avg_ms": round(statistics.mean(latencies), 2),
        "median_ms": round(statistics.median(latencies), 2),
        "p95_ms": round(sorted(latencies)[int(runs * 0.95)], 2),
        "max_ms": round(max(latencies), 2),
    }


def bench_aggregation_latency(es: Elasticsearch, index: str, runs: int = 30) -> dict:
    """Run geohash_grid aggregation and measure latency."""
    latencies: list[float] = []
    for _ in range(runs):
        body = {
            "size": 0,
            "aggs": {
                "grid": {
                    "geohash_grid": {"field": "location", "precision": 5},
                    "aggs": {"vehicles": {"cardinality": {"field": "vehicle"}}},
                }
            },
        }
        t0 = time.perf_counter()
        es.search(index=index, **body)
        latencies.append((time.perf_counter() - t0) * 1000)

    return {
        "runs": runs,
        "min_ms": round(min(latencies), 2),
        "avg_ms": round(statistics.mean(latencies), 2),
        "median_ms": round(statistics.median(latencies), 2),
        "p95_ms": round(sorted(latencies)[int(runs * 0.95)], 2),
        "max_ms": round(max(latencies), 2),
    }


def bench_scalability(es: Elasticsearch, index: str) -> list[dict]:
    """Insert increasing volumes and measure throughput + search latency at each level."""
    sizes = [1_000, 5_000, 10_000, 50_000]
    results = []
    total_indexed = 0

    for n in sizes:
        ix = bench_indexing(es, index, n)
        total_indexed += n

        sl = bench_search_latency(es, index, runs=20)

        results.append({
            "cumulative_docs": total_indexed,
            "batch_size": n,
            "index_docs_per_sec": ix["docs_per_sec"],
            "search_avg_ms": sl["avg_ms"],
            "search_p95_ms": sl["p95_ms"],
        })
        print(f"  scale test: {total_indexed} docs indexed")

    return results


# ─── main ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Elasticsearch benchmark")
    parser.add_argument("--es-host", default="http://localhost:9200")
    parser.add_argument("--index", default="bench_bus_waypoints")
    args = parser.parse_args()

    es = Elasticsearch(args.es_host)
    index = args.index

    if es.indices.exists(index=index):
        es.indices.delete(index=index)
    es.indices.create(index=index, **{
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "properties": {
                "vehicle": {"type": "keyword"},
                "datetime": {"type": "date"},
                "location": {"type": "geo_point"},
                "speed": {"type": "float"},
                "ignition": {"type": "boolean"},
            }
        },
    })

    print("\n=== 1. Indexing throughput (10k docs) ===")
    ix = bench_indexing(es, index, 10_000)
    print(tabulate([ix], headers="keys", tablefmt="github"))

    print("\n=== 2. Geo search latency (50 queries) ===")
    sl = bench_search_latency(es, index, runs=50)
    print(tabulate([sl], headers="keys", tablefmt="github"))

    print("\n=== 3. Aggregation latency (30 queries) ===")
    al = bench_aggregation_latency(es, index, runs=30)
    print(tabulate([al], headers="keys", tablefmt="github"))

    print("\n=== 4. Scalability test ===")
    es.indices.delete(index=index)
    es.indices.create(index=index, **{
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "properties": {
                "vehicle": {"type": "keyword"},
                "datetime": {"type": "date"},
                "location": {"type": "geo_point"},
                "speed": {"type": "float"},
                "ignition": {"type": "boolean"},
            }
        },
    })
    sc = bench_scalability(es, index)
    print(tabulate(sc, headers="keys", tablefmt="github"))

    es.indices.delete(index=index, ignore=[404])
    print("\nBenchmark complete. Temp index cleaned up.")


if __name__ == "__main__":
    main()
