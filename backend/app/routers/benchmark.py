"""Benchmark router — runs performance benchmarks via the backend (which has ES access)."""

from __future__ import annotations

import random
import statistics
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from elasticsearch import Elasticsearch, helpers

from ..dependencies import get_es_client

router = APIRouter()

# ─── Synthetic data ──────────────────────────────────────────────────

HCM_LAT = (10.70, 10.90)
HCM_LON = (106.60, 106.80)
BENCH_VEHICLES = [f"vehicle_{i:04d}" for i in range(200)]
BENCH_INDEX = "bench_bus_waypoints_api"

BENCH_MAPPING = {
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
}


def _random_doc() -> dict:
    return {
        "vehicle": random.choice(BENCH_VEHICLES),
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


# ─── Benchmark functions ─────────────────────────────────────────────

def _bench_indexing(es: Elasticsearch, index: str, n: int) -> dict:
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


def _bench_search_latency(es: Elasticsearch, index: str, runs: int = 50) -> dict:
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


def _bench_aggregation_latency(es: Elasticsearch, index: str, runs: int = 30) -> dict:
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


# ─── Endpoints ───────────────────────────────────────────────────────

@router.get("")
async def benchmark_info() -> dict:
    """Confirm benchmark router is mounted. Use POST /api/benchmark/run to run."""
    return {"status": "ok", "run": "POST /api/benchmark/run"}


@router.post("/run")
async def run_benchmark(
    es: Elasticsearch = Depends(get_es_client),
) -> dict:
    """Run all benchmark tests and return results."""
    index = BENCH_INDEX

    # Setup
    if es.indices.exists(index=index):
        es.indices.delete(index=index)
    es.indices.create(index=index, **BENCH_MAPPING)

    try:
        # 1. Indexing throughput
        indexing = _bench_indexing(es, index, 10_000)

        # 2. Search latency
        search = _bench_search_latency(es, index, runs=50)

        # 3. Aggregation latency
        aggregation = _bench_aggregation_latency(es, index, runs=30)

        # 4. Scalability
        es.indices.delete(index=index)
        es.indices.create(index=index, **BENCH_MAPPING)

        scalability = []
        total_indexed = 0
        for n in [1_000, 5_000, 10_000, 25_000]:
            ix = _bench_indexing(es, index, n)
            total_indexed += n
            sl = _bench_search_latency(es, index, runs=20)
            scalability.append({
                "cumulative_docs": total_indexed,
                "batch_size": n,
                "index_docs_per_sec": ix["docs_per_sec"],
                "search_avg_ms": sl["avg_ms"],
                "search_p95_ms": sl["p95_ms"],
            })

        return {
            "indexing": indexing,
            "search_latency": search,
            "aggregation_latency": aggregation,
            "scalability": scalability,
        }
    finally:
        # Cleanup
        if es.indices.exists(index=index):
            es.indices.delete(index=index, ignore=[404])
