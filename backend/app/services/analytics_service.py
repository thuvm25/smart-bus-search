"""Analytics service — real Elasticsearch aggregation queries."""

from __future__ import annotations

from elasticsearch import Elasticsearch


def geo_grid_density(
    es: Elasticsearch,
    index: str,
    precision: int = 5,
    minutes: int | None = None,
) -> dict:
    """Bus density per geohash cell (heatmap data).

    Args:
        precision: geohash precision (1‑12). 5 ≈ 5km cells, 6 ≈ 1km, 7 ≈ 150m.
        minutes: optional time window — only count records from last N minutes.
    """
    filters: list[dict] = []
    if minutes:
        filters.append({"range": {"datetime": {"gte": f"now-{minutes}m"}}})

    query: dict = {"match_all": {}} if not filters else {"bool": {"filter": filters}}

    body = {
        "size": 0,
        "query": query,
        "aggs": {
            "grid": {
                "geohash_grid": {
                    "field": "location",
                    "precision": precision,
                },
                "aggs": {
                    "center": {"geo_centroid": {"field": "location"}},
                    "unique_vehicles": {"cardinality": {"field": "vehicle"}},
                },
            }
        },
    }

    resp = es.search(index=index, **body)
    buckets = resp["aggregations"]["grid"]["buckets"]
    cells = []
    for b in buckets:
        loc = b["center"]["location"]
        cells.append({
            "geohash": b["key"],
            "doc_count": b["doc_count"],
            "unique_vehicles": b["unique_vehicles"]["value"],
            "lat": loc["lat"],
            "lon": loc["lon"],
        })
    return {"cells": cells, "total_cells": len(cells)}


def active_vehicles_count(
    es: Elasticsearch,
    index: str,
    minutes: int = 5,
) -> dict:
    """Count distinct vehicles active in the last N minutes."""
    body = {
        "size": 0,
        "query": {"range": {"datetime": {"gte": f"now-{minutes}m"}}},
        "aggs": {
            "unique_vehicles": {"cardinality": {"field": "vehicle"}},
            "total_records": {"value_count": {"field": "vehicle"}},
        },
    }
    resp = es.search(index=index, **body)
    aggs = resp["aggregations"]
    return {
        "active_vehicles": aggs["unique_vehicles"]["value"],
        "total_records": int(aggs["total_records"]["value"]),
        "time_window_minutes": minutes,
    }


def speed_statistics(
    es: Elasticsearch,
    index: str,
    minutes: int | None = None,
) -> dict:
    """Aggregate min / avg / max speed across all records."""
    filters: list[dict] = [{"exists": {"field": "speed"}}]
    if minutes:
        filters.append({"range": {"datetime": {"gte": f"now-{minutes}m"}}})

    body = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "speed_stats": {"extended_stats": {"field": "speed"}},
            "speed_histogram": {
                "histogram": {"field": "speed", "interval": 10},
            },
        },
    }
    resp = es.search(index=index, **body)
    stats = resp["aggregations"]["speed_stats"]
    hist = resp["aggregations"]["speed_histogram"]["buckets"]
    return {
        "count": stats["count"],
        "min": stats["min"],
        "max": stats["max"],
        "avg": round(stats["avg"], 2) if stats["avg"] else None,
        "std_deviation": round(stats["std_deviation"], 2) if stats.get("std_deviation") else None,
        "histogram": [{"speed_range": f"{int(b['key'])}-{int(b['key'])+10}", "count": b["doc_count"]} for b in hist],
    }


def timeline(
    es: Elasticsearch,
    index: str,
    minutes: int = 60,
    interval: str = "5m",
) -> dict:
    """Time-bucketed vehicle activity: how many buses were active per interval.

    Args:
        minutes: look-back window (default 60).
        interval: bucket size — e.g. '5m', '15m', '1h'.
    """
    body = {
        "size": 0,
        "query": {"range": {"datetime": {"gte": f"now-{minutes}m"}}},
        "aggs": {
            "over_time": {
                "date_histogram": {
                    "field": "datetime",
                    "fixed_interval": interval,
                    "min_doc_count": 0,
                    "extended_bounds": {
                        "min": f"now-{minutes}m",
                        "max": "now",
                    },
                },
                "aggs": {
                    "unique_vehicles": {"cardinality": {"field": "vehicle"}},
                },
            }
        },
    }
    resp = es.search(index=index, **body)
    buckets = resp["aggregations"]["over_time"]["buckets"]
    points = [
        {
            "datetime": b["key_as_string"],
            "records": b["doc_count"],
            "unique_vehicles": b["unique_vehicles"]["value"],
        }
        for b in buckets
    ]
    return {
        "points": points,
        "total_buckets": len(points),
        "interval": interval,
        "time_window_minutes": minutes,
    }


def route_stats(
    es: Elasticsearch,
    index: str,
    minutes: int | None = None,
) -> dict:
    """Per-route aggregation: bus count, avg speed, record count per route."""
    filters: list[dict] = [{"exists": {"field": "route_no"}}]
    if minutes:
        filters.append({"range": {"datetime": {"gte": f"now-{minutes}m"}}})

    body = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "by_route": {
                "terms": {"field": "route_no", "size": 500},
                "aggs": {
                    "unique_vehicles": {"cardinality": {"field": "vehicle"}},
                    "avg_speed": {"avg": {"field": "speed"}},
                    "latest": {"max": {"field": "datetime"}},
                },
            }
        },
    }
    resp = es.search(index=index, **body)
    buckets = resp["aggregations"]["by_route"]["buckets"]
    routes = [
        {
            "route_no": b["key"],
            "record_count": b["doc_count"],
            "unique_vehicles": b["unique_vehicles"]["value"],
            "avg_speed": round(b["avg_speed"]["value"], 2) if b["avg_speed"]["value"] is not None else None,
            "latest_record": b["latest"]["value_as_string"] if b["latest"].get("value_as_string") else None,
        }
        for b in buckets
    ]
    routes.sort(key=lambda r: r["unique_vehicles"], reverse=True)
    return {"routes": routes, "total_routes": len(routes)}


def index_stats(es: Elasticsearch, index: str) -> dict:
    """Basic index statistics for the dashboard."""
    try:
        stats = es.indices.stats(index=index)
        idx = stats["indices"][index]
        total = idx["total"]
        return {
            "doc_count": total["docs"]["count"],
            "size_bytes": total["store"]["size_in_bytes"],
            "size_mb": round(total["store"]["size_in_bytes"] / 1_048_576, 2),
            "indexing_total": total["indexing"]["index_total"],
            "search_total": total["search"]["query_total"],
        }
    except Exception:
        return {}
