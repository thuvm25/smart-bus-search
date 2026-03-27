"""
Setup Kibana: Data View + Visualizations + Dashboard for Smart Bus GPS.

Demonstrates:
  1. Real-time data ingestion  → metric tile + time-series bar chart
  2. Geospatial search         → Maps layer (bus positions)
  3. Time-based queries        → date histogram (records/minute)
  4. Vehicle trajectory        → data table (top vehicles + speed)

Usage:
  python scripts/setup_kibana.py
  # or with custom host:
  KIBANA_HOST=http://localhost:5601 python scripts/setup_kibana.py
"""

import json
import os
import sys
import time

try:
    import requests
except ImportError:
    print("pip install requests  # then re-run")
    sys.exit(1)

KIBANA = os.getenv("KIBANA_HOST", "http://localhost:5601")
ES     = os.getenv("ES_HOST",     "http://localhost:9200")
INDEX  = os.getenv("ES_INDEX",    "bus_waypoints")
HEADERS = {"kbn-xsrf": "true", "Content-Type": "application/json"}


# ─── helpers ──────────────────────────────────────────────────────────────────
def post(path, body):
    r = requests.post(f"{KIBANA}{path}", headers=HEADERS, json=body, timeout=15)
    if r.status_code not in (200, 201):
        print(f"  WARN {path} → {r.status_code}: {r.text[:200]}")
    return r

def put(path, body):
    r = requests.put(f"{KIBANA}{path}", headers=HEADERS, json=body, timeout=15)
    if r.status_code not in (200, 201):
        print(f"  WARN {path} → {r.status_code}: {r.text[:200]}")
    return r


# ─── 1. Data View ─────────────────────────────────────────────────────────────
def create_data_view():
    print("[1] Creating data view...")
    body = {
        "data_view": {
            "id":          "bus_waypoints_dv",
            "title":       INDEX,
            "timeFieldName": "@timestamp",
            "name":        "Smart Bus GPS",
        },
        "override": True,
    }
    r = post("/api/data_views/data_view", body)
    dv_id = r.json().get("data_view", {}).get("id", "bus_waypoints_dv")
    print(f"   Data view id: {dv_id}")
    return dv_id


# ─── 2. Saved Objects (visualizations + map + dashboard) ──────────────────────
def create_saved_objects(dv_id: str):
    print("[2] Creating saved objects...")

    objects = [

        # ── VIS 1: Total Records (metric) ─────────────────────────────────────
        {
            "id": "bus-metric-total",
            "type": "visualization",
            "attributes": {
                "title": "📡 Total GPS Pings",
                "visState": json.dumps({
                    "title": "Total GPS Pings",
                    "type": "metric",
                    "params": {
                        "addTooltip": True,
                        "addLegend": False,
                        "type": "metric",
                        "metric": {
                            "percentageMode": False,
                            "useRanges": False,
                            "colorSchema": "Green to Red",
                            "metricColorMode": "None",
                            "colorsRange": [{"from": 0, "to": 10000}],
                            "labels": {"show": True},
                            "invertColors": False,
                            "style": {
                                "bgFill": "#000",
                                "bgColor": False,
                                "labelColor": False,
                                "subText": "",
                                "fontSize": 60,
                            },
                        },
                    },
                    "aggs": [{
                        "id": "1",
                        "enabled": True,
                        "type": "count",
                        "params": {},
                        "schema": "metric",
                    }],
                }),
                "uiStateJSON": "{}",
                "description": "",
                "kibanaSavedObjectMeta": {
                    "searchSourceJSON": json.dumps({
                        "index": dv_id,
                        "query": {"query": "", "language": "kuery"},
                        "filter": [],
                    })
                },
            },
            "references": [{"id": dv_id, "name": "kibanaSavedObjectMeta.searchSourceJSON.index", "type": "index-pattern"}],
        },

        # ── VIS 2: Active Vehicles (metric) ───────────────────────────────────
        {
            "id": "bus-metric-vehicles",
            "type": "visualization",
            "attributes": {
                "title": "🚌 Active Vehicles",
                "visState": json.dumps({
                    "title": "Active Vehicles",
                    "type": "metric",
                    "params": {
                        "addTooltip": True,
                        "addLegend": False,
                        "type": "metric",
                        "metric": {
                            "percentageMode": False,
                            "useRanges": False,
                            "colorSchema": "Green to Red",
                            "metricColorMode": "None",
                            "colorsRange": [{"from": 0, "to": 1000}],
                            "labels": {"show": True},
                            "invertColors": False,
                            "style": {"bgFill": "#000", "bgColor": False, "labelColor": False, "subText": "", "fontSize": 60},
                        },
                    },
                    "aggs": [{
                        "id": "1",
                        "enabled": True,
                        "type": "cardinality",
                        "params": {"field": "vehicle"},
                        "schema": "metric",
                    }],
                }),
                "uiStateJSON": "{}",
                "description": "",
                "kibanaSavedObjectMeta": {
                    "searchSourceJSON": json.dumps({
                        "index": dv_id,
                        "query": {"query": "", "language": "kuery"},
                        "filter": [],
                    })
                },
            },
            "references": [{"id": dv_id, "name": "kibanaSavedObjectMeta.searchSourceJSON.index", "type": "index-pattern"}],
        },

        # ── VIS 3: GPS Pings per Minute (date histogram) ─────────────────────
        {
            "id": "bus-histogram-time",
            "type": "visualization",
            "attributes": {
                "title": "⏱ GPS Pings / Minute (Real-time Ingestion)",
                "visState": json.dumps({
                    "title": "GPS Pings per Minute",
                    "type": "histogram",
                    "params": {
                        "type": "histogram",
                        "grid": {"categoryLines": False},
                        "categoryAxes": [{"id": "CategoryAxis-1", "type": "category", "position": "bottom", "show": True,
                                          "scale": {"type": "linear"}, "labels": {"show": True, "truncate": 100},
                                          "title": {}}],
                        "valueAxes": [{"id": "ValueAxis-1", "name": "LeftAxis-1", "type": "value", "position": "left",
                                       "show": True, "scale": {"type": "linear", "mode": "normal"},
                                       "labels": {"show": True, "rotate": 0, "filter": False, "truncate": 100},
                                       "title": {"text": "Records"}}],
                        "seriesParams": [{"show": True, "type": "histogram", "mode": "stacked",
                                          "data": {"label": "Count", "id": "1"},
                                          "valueAxis": "ValueAxis-1", "drawLinesBetweenPoints": True,
                                          "lineWidth": 2, "showCircles": True}],
                        "addTooltip": True,
                        "addLegend": True,
                        "legendPosition": "right",
                        "times": [],
                        "addTimeMarker": True,
                        "thresholdLine": {"show": False, "value": 10, "width": 1, "style": "full", "color": "#E7664C"},
                        "labels": {},
                    },
                    "aggs": [
                        {"id": "1", "enabled": True, "type": "count", "params": {}, "schema": "metric"},
                        {"id": "2", "enabled": True, "type": "date_histogram",
                         "params": {"field": "@timestamp", "timeRange": {"from": "now-15m", "to": "now"},
                                    "useNormalizedEsInterval": True, "scaleMetricValues": False,
                                    "interval": "auto", "drop_partials": False, "min_doc_count": 1, "extended_bounds": {}},
                         "schema": "segment"},
                    ],
                }),
                "uiStateJSON": "{}",
                "description": "Records arriving per minute — demonstrates real-time ingestion",
                "kibanaSavedObjectMeta": {
                    "searchSourceJSON": json.dumps({
                        "index": dv_id,
                        "query": {"query": "", "language": "kuery"},
                        "filter": [],
                    })
                },
            },
            "references": [{"id": dv_id, "name": "kibanaSavedObjectMeta.searchSourceJSON.index", "type": "index-pattern"}],
        },

        # ── VIS 4: Speed Distribution (horizontal bar) ────────────────────────
        {
            "id": "bus-speed-dist",
            "type": "visualization",
            "attributes": {
                "title": "🚀 Speed Distribution by Route",
                "visState": json.dumps({
                    "title": "Speed Distribution",
                    "type": "histogram",
                    "params": {
                        "type": "histogram",
                        "grid": {"categoryLines": False},
                        "categoryAxes": [{"id": "CategoryAxis-1", "type": "category", "position": "bottom", "show": True,
                                          "scale": {"type": "linear"}, "labels": {"show": True, "truncate": 100}, "title": {}}],
                        "valueAxes": [{"id": "ValueAxis-1", "name": "LeftAxis-1", "type": "value", "position": "left",
                                       "show": True, "scale": {"type": "linear", "mode": "normal"},
                                       "labels": {"show": True, "rotate": 0, "filter": False, "truncate": 100},
                                       "title": {"text": "Count"}}],
                        "seriesParams": [{"show": True, "type": "histogram", "mode": "stacked",
                                          "data": {"label": "Count", "id": "1"},
                                          "valueAxis": "ValueAxis-1", "drawLinesBetweenPoints": True,
                                          "lineWidth": 2, "showCircles": True}],
                        "addTooltip": True, "addLegend": True, "legendPosition": "right",
                        "times": [], "addTimeMarker": False,
                        "thresholdLine": {"show": False, "value": 10, "width": 1, "style": "full", "color": "#E7664C"},
                        "labels": {},
                    },
                    "aggs": [
                        {"id": "1", "enabled": True, "type": "count", "params": {}, "schema": "metric"},
                        {"id": "2", "enabled": True, "type": "histogram",
                         "params": {"field": "speed", "interval": 5, "min_doc_count": True,
                                    "has_extended_bounds": False, "extended_bounds": {"min": "", "max": ""},
                                    "customLabel": "Speed (km/h)"},
                         "schema": "segment"},
                    ],
                }),
                "uiStateJSON": "{}",
                "description": "",
                "kibanaSavedObjectMeta": {
                    "searchSourceJSON": json.dumps({
                        "index": dv_id,
                        "query": {"query": "", "language": "kuery"},
                        "filter": [],
                    })
                },
            },
            "references": [{"id": dv_id, "name": "kibanaSavedObjectMeta.searchSourceJSON.index", "type": "index-pattern"}],
        },

        # ── VIS 5: Top Routes by activity ─────────────────────────────────────
        {
            "id": "bus-top-routes",
            "type": "visualization",
            "attributes": {
                "title": "🗺 Top Routes by Pings",
                "visState": json.dumps({
                    "title": "Top Routes",
                    "type": "pie",
                    "params": {
                        "type": "pie",
                        "addTooltip": True,
                        "addLegend": True,
                        "legendPosition": "right",
                        "isDonut": True,
                        "labels": {"show": False, "values": True, "last_level": True, "truncate": 100},
                    },
                    "aggs": [
                        {"id": "1", "enabled": True, "type": "count", "params": {}, "schema": "metric"},
                        {"id": "2", "enabled": True, "type": "terms",
                         "params": {"field": "route_no", "orderBy": "1", "order": "desc",
                                    "size": 10, "otherBucket": True, "otherBucketLabel": "Other",
                                    "missingBucket": False, "missingBucketLabel": "Missing",
                                    "customLabel": "Route"},
                         "schema": "segment"},
                    ],
                }),
                "uiStateJSON": "{}",
                "description": "",
                "kibanaSavedObjectMeta": {
                    "searchSourceJSON": json.dumps({
                        "index": dv_id,
                        "query": {"query": "", "language": "kuery"},
                        "filter": [],
                    })
                },
            },
            "references": [{"id": dv_id, "name": "kibanaSavedObjectMeta.searchSourceJSON.index", "type": "index-pattern"}],
        },

        # ── VIS 6: Vehicle Trajectory Table ───────────────────────────────────
        {
            "id": "bus-trajectory-table",
            "type": "visualization",
            "attributes": {
                "title": "🛣 Vehicle Trajectory (Recent Pings)",
                "visState": json.dumps({
                    "title": "Vehicle Trajectory",
                    "type": "table",
                    "params": {
                        "perPage": 15,
                        "showPartialRows": False,
                        "showMetricsAtAllLevels": False,
                        "sort": {"columnIndex": None, "direction": None},
                        "showTotal": False,
                        "totalFunc": "sum",
                        "percentageCol": "",
                    },
                    "aggs": [
                        {"id": "1", "enabled": True, "type": "count", "params": {"customLabel": "Pings"}, "schema": "metric"},
                        {"id": "2", "enabled": True, "type": "terms",
                         "params": {"field": "vehicle", "orderBy": "1", "order": "desc", "size": 15,
                                    "otherBucket": False, "customLabel": "Vehicle ID"},
                         "schema": "bucket"},
                        {"id": "3", "enabled": True, "type": "terms",
                         "params": {"field": "route_name.keyword", "orderBy": "_key", "order": "asc", "size": 1,
                                    "otherBucket": False, "customLabel": "Route"},
                         "schema": "bucket"},
                        {"id": "4", "enabled": True, "type": "avg",
                         "params": {"field": "speed", "customLabel": "Avg Speed (km/h)"},
                         "schema": "metric"},
                    ],
                }),
                "uiStateJSON": json.dumps({"vis": {"params": {"sort": {"columnIndex": 0, "direction": "desc"}}}}),
                "description": "Most active vehicles — supports trajectory queries",
                "kibanaSavedObjectMeta": {
                    "searchSourceJSON": json.dumps({
                        "index": dv_id,
                        "query": {"query": "", "language": "kuery"},
                        "filter": [],
                    })
                },
            },
            "references": [{"id": dv_id, "name": "kibanaSavedObjectMeta.searchSourceJSON.index", "type": "index-pattern"}],
        },

        # ── MAP: Bus Positions ─────────────────────────────────────────────────
        {
            "id": "bus-map-positions",
            "type": "map",
            "attributes": {
                "title": "🗺 Bus Positions (Live Map)",
                "description": "Real-time bus positions — geospatial search demo",
                "mapStateJSON": json.dumps({
                    "zoom": 11,
                    "center": {"lon": 106.66, "lat": 10.78},  # Ho Chi Minh City center
                    "timeFilters": {"from": "now-15m", "to": "now"},
                    "query": {"language": "kuery", "query": ""},
                    "filters": [],
                    "settings": {"hideable": False},
                }),
                "layerListJSON": json.dumps([
                    {
                        "id": "base_layer",
                        "type": "TILE",
                        "sourceDescriptor": {
                            "type": "EMS_TMS",
                            "isAutoSelect": True,
                        },
                        "visible": True,
                        "style": {},
                        "label": "Base Map",
                        "minZoom": 0,
                        "maxZoom": 24,
                        "alpha": 1,
                    },
                    {
                        "id": "bus_positions",
                        "label": "Bus Positions",
                        "minZoom": 0,
                        "maxZoom": 24,
                        "alpha": 0.75,
                        "visible": True,
                        "style": {
                            "type": "VECTOR",
                            "properties": {
                                "fillColor": {
                                    "type": "DYNAMIC",
                                    "options": {
                                        "field": {"name": "speed", "origin": "source"},
                                        "color": "Blues",
                                        "fieldMetaOptions": {"isEnabled": True, "sigma": 3},
                                    },
                                },
                                "lineColor": {"type": "STATIC", "options": {"color": "#FFFFFF"}},
                                "lineWidth": {"type": "STATIC", "options": {"size": 1}},
                                "iconSize": {"type": "STATIC", "options": {"size": 6}},
                                "symbolizeAs": {"options": {"value": "circle"}},
                                "icon": {"type": "STATIC", "options": {"value": "marker"}},
                            },
                        },
                        "type": "GEOJSON_VECTOR",
                        "sourceDescriptor": {
                            "id": "bus_positions_src",
                            "type": "ES_SEARCH",
                            "geoField": "location",
                            "limit": 2048,
                            "filterByMapBounds": True,
                            "tooltipProperties": ["vehicle", "route_no", "route_name", "speed", "datetime"],
                            "scalingType": "LIMIT",
                            "indexPatternRefName": "layer_0_source_index_pattern",
                            "applyGlobalQuery": True,
                            "applyGlobalTime": True,
                        },
                        "joins": [],
                    },
                ]),
                "uiStateJSON": "{}",
            },
            "references": [
                {
                    "id": dv_id,
                    "name": "layer_0_source_index_pattern",
                    "type": "index-pattern",
                },
            ],
        },

        # ── DASHBOARD ──────────────────────────────────────────────────────────
        {
            "id": "smart-bus-dashboard",
            "type": "dashboard",
            "attributes": {
                "title": "🚌 Smart Bus GPS — Real-time Dashboard",
                "description": "Demo: real-time ingestion | geospatial | time-based | trajectory queries",
                "panelsJSON": json.dumps([
                    # Row 1: metrics
                    {"version": "8.15.0", "type": "visualization", "gridData": {"x": 0,  "y": 0, "w": 12, "h": 8, "i": "p1"}, "panelIndex": "p1", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p1"},
                    {"version": "8.15.0", "type": "visualization", "gridData": {"x": 12, "y": 0, "w": 12, "h": 8, "i": "p2"}, "panelIndex": "p2", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p2"},
                    # Row 1: time histogram
                    {"version": "8.15.0", "type": "visualization", "gridData": {"x": 24, "y": 0, "w": 24, "h": 8, "i": "p3"}, "panelIndex": "p3", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p3"},
                    # Row 2: map (large)
                    {"version": "8.15.0", "type": "map",           "gridData": {"x": 0,  "y": 8, "w": 32, "h": 24, "i": "p4"}, "panelIndex": "p4", "embeddableConfig": {"enhancements": {}, "isLayerTOCOpen": False, "mapCenter": {"lat": 10.78, "lon": 106.66, "zoom": 11}, "mapBuffer": {"minLon": 106.5, "minLat": 10.6, "maxLon": 106.8, "maxLat": 10.9}, "openTOCDetails": []}, "panelRefName": "panel_p4"},
                    # Row 2: right side
                    {"version": "8.15.0", "type": "visualization", "gridData": {"x": 32, "y": 8, "w": 16, "h": 12, "i": "p5"}, "panelIndex": "p5", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p5"},
                    {"version": "8.15.0", "type": "visualization", "gridData": {"x": 32, "y": 20, "w": 16, "h": 12, "i": "p6"}, "panelIndex": "p6", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p6"},
                    # Row 3: trajectory table
                    {"version": "8.15.0", "type": "visualization", "gridData": {"x": 0,  "y": 32, "w": 48, "h": 14, "i": "p7"}, "panelIndex": "p7", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p7"},
                ]),
                "optionsJSON": json.dumps({
                    "useMargins": True,
                    "syncColors": False,
                    "syncCursor": True,
                    "syncTooltips": False,
                    "hidePanelTitles": False,
                }),
                "timeRestore": True,
                "timeTo": "now",
                "timeFrom": "now-15m",
                "refreshInterval": {"pause": False, "value": 5000},  # auto-refresh 5s
                "kibanaSavedObjectMeta": {
                    "searchSourceJSON": json.dumps({"query": {"query": "", "language": "kuery"}, "filter": []}),
                },
            },
            "references": [
                {"id": "bus-metric-total",     "name": "panel_p1", "type": "visualization"},
                {"id": "bus-metric-vehicles",  "name": "panel_p2", "type": "visualization"},
                {"id": "bus-histogram-time",   "name": "panel_p3", "type": "visualization"},
                {"id": "bus-map-positions",    "name": "panel_p4", "type": "map"},
                {"id": "bus-speed-dist",       "name": "panel_p5", "type": "visualization"},
                {"id": "bus-top-routes",       "name": "panel_p6", "type": "visualization"},
                {"id": "bus-trajectory-table", "name": "panel_p7", "type": "visualization"},
            ],
        },
    ]

    r = post("/api/saved_objects/_bulk_create?overwrite=true", objects)
    results = r.json()
    saved = results.get("saved_objects", [])
    ok  = [o for o in saved if not o.get("error")]
    err = [o for o in saved if o.get("error")]
    print(f"   Created {len(ok)} objects, {len(err)} errors")
    for e in err:
        print(f"   ERROR: {e['id']} — {e['error']}")
    return len(err) == 0


# ─── 3. Verify ────────────────────────────────────────────────────────────────
def verify():
    print("[3] Verifying...")
    r = requests.get(f"{KIBANA}/api/saved_objects/dashboard/smart-bus-dashboard",
                     headers=HEADERS, timeout=10)
    if r.status_code == 200:
        print(f"   Dashboard URL: {KIBANA}/app/dashboards#/view/smart-bus-dashboard")
        print(f"   Maps URL:      {KIBANA}/app/maps")
        return True
    print(f"   Dashboard not found: {r.status_code}")
    return False


# ─── main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  Kibana Setup — Smart Bus GPS Dashboard")
    print(f"  Kibana : {KIBANA}")
    print(f"  Index  : {INDEX}")
    print("=" * 60)

    # Wait for Kibana
    for _ in range(10):
        try:
            r = requests.get(f"{KIBANA}/api/status", timeout=5)
            if r.status_code == 200:
                break
        except Exception:
            pass
        print("  Waiting for Kibana...")
        time.sleep(3)

    dv_id = create_data_view()
    ok    = create_saved_objects(dv_id)
    if ok:
        verify()
    print("=" * 60)
    print("  Done! Open Kibana and navigate to Dashboards.")
    print("=" * 60)


if __name__ == "__main__":
    main()
