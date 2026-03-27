"""
Setup Kibana: Data View + Visualizations + Dashboard for Smart Bus GPS.

Usage:
  source .venv/bin/activate
  python scripts/setup_kibana.py

Environment variables:
  KIBANA_HOST  – default http://localhost:5601
  ES_INDEX     – default bus_waypoints
"""

import json
import os
import sys
import time

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

KIBANA  = os.getenv("KIBANA_HOST", "http://localhost:5601")
INDEX   = os.getenv("ES_INDEX", "bus_waypoints")
HEADERS = {"kbn-xsrf": "true", "Content-Type": "application/json"}


# ── helpers ───────────────────────────────────────────────────────────────────
def wait_for_kibana():
    print("Waiting for Kibana...")
    for _ in range(24):
        try:
            r = requests.get(f"{KIBANA}/api/status", timeout=5)
            if r.status_code == 200:
                lvl = r.json().get("status", {}).get("overall", {}).get("level", "")
                if lvl == "available":
                    print("  Kibana ready.")
                    return
        except Exception:
            pass
        time.sleep(5)
    print("ERROR: Kibana not available after 2 minutes")
    sys.exit(1)


def create(obj_type, obj_id, attributes, references=None):
    body = {"attributes": attributes}
    if references:
        body["references"] = references
    r = requests.post(
        f"{KIBANA}/api/saved_objects/{obj_type}/{obj_id}?overwrite=true",
        headers=HEADERS, json=body, timeout=15,
    )
    ok = r.status_code in (200, 201)
    print(f"  {'OK' if ok else 'FAIL'} {obj_type}/{obj_id}" +
          ("" if ok else f" — {r.text[:120]}"))
    return ok


def bulk_create(objects):
    r = requests.post(
        f"{KIBANA}/api/saved_objects/_bulk_create?overwrite=true",
        headers=HEADERS, json=objects, timeout=30,
    )
    for o in r.json().get("saved_objects", []):
        err = o.get("error")
        print(f"  {'OK' if not err else 'FAIL'} {o['type']}/{o['id']}" +
              (f" — {err}" if err else ""))


# ── 1. Data View ──────────────────────────────────────────────────────────────
def setup_data_view():
    print("\n[1] Data view")
    r = requests.post(
        f"{KIBANA}/api/data_views/data_view",
        headers=HEADERS,
        json={
            "data_view": {
                "id": "bus_waypoints_dv",
                "title": INDEX,
                "timeFieldName": "@timestamp",
                "name": "Smart Bus GPS",
            },
            "override": True,
        },
        timeout=15,
    )
    dv_id = r.json().get("data_view", {}).get("id", "bus_waypoints_dv")
    print(f"  data view id: {dv_id}")
    return dv_id


# ── 2. Metric visualizations (legacy — work in all Kibana 8.x) ───────────────
def setup_metrics(dv_id):
    print("\n[2] Metric tiles")

    def metric_vis(title, agg_type, field=None):
        agg = {"id": "1", "enabled": True, "type": agg_type,
               "params": {"field": field} if field else {}, "schema": "metric"}
        return {
            "title": title,
            "visState": json.dumps({
                "title": title, "type": "metric",
                "params": {
                    "addTooltip": True, "addLegend": False, "type": "metric",
                    "metric": {
                        "percentageMode": False, "useRanges": False,
                        "colorSchema": "Green to Red", "metricColorMode": "None",
                        "colorsRange": [{"from": 0, "to": 10000}],
                        "labels": {"show": True}, "invertColors": False,
                        "style": {"bgFill": "#000", "bgColor": False,
                                  "labelColor": False, "subText": "", "fontSize": 60},
                    },
                },
                "aggs": [agg],
            }),
            "uiStateJSON": "{}",
            "description": "",
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps({
                    "index": dv_id,
                    "query": {"query": "", "language": "kuery"},
                    "filter": [],
                }),
            },
        }

    REF = [{"id": dv_id, "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
            "type": "index-pattern"}]
    bulk_create([
        {"id": "bus-metric-total",    "type": "visualization",
         "attributes": metric_vis("📡 Total GPS Pings",    "count"),       "references": REF},
        {"id": "bus-metric-vehicles", "type": "visualization",
         "attributes": metric_vis("🚌 Active Vehicles",    "cardinality", "vehicle"), "references": REF},
    ])


# ── 3. Lens visualizations ────────────────────────────────────────────────────
def setup_lens(dv_id):
    print("\n[3] Lens charts")
    REF = [{"id": dv_id, "name": "indexpattern-datasource-layer-layer1",
            "type": "index-pattern"}]

    def xy_layer(col_x, col_y, series_type="bar_stacked", color="#00B3A4"):
        return {
            "layerId": "layer1", "layerType": "data",
            "accessors": [col_y], "seriesType": series_type,
            "xAccessor": col_x,
            "yConfig": [{"forAccessor": col_y, "color": color}],
        }

    # GPS Pings per minute
    bulk_create([{
        "id": "bus-histogram-time", "type": "lens",
        "attributes": {
            "title": "⏱ GPS Pings / Minute",
            "visualizationType": "lnsXY",
            "state": {
                "datasourceStates": {"formBased": {"layers": {"layer1": {
                    "columnOrder": ["col_time", "col_count"],
                    "columns": {
                        "col_time": {
                            "label": "Time", "dataType": "date",
                            "operationType": "date_histogram",
                            "sourceField": "@timestamp",
                            "isBucketed": True, "scale": "interval",
                            "params": {"interval": "auto", "includeEmptyRows": True},
                        },
                        "col_count": {
                            "label": "GPS Pings", "dataType": "number",
                            "operationType": "count", "isBucketed": False,
                            "scale": "ratio", "sourceField": "___records___",
                        },
                    },
                    "incompleteColumns": {},
                }}}},
                "visualization": {
                    "legend": {"isVisible": True, "position": "bottom"},
                    "preferredSeriesType": "bar_stacked",
                    "layers": [xy_layer("col_time", "col_count")],
                },
                "query": {"query": "", "language": "kuery"}, "filters": [],
            },
        },
        "references": REF,
    }])

    # Speed distribution
    bulk_create([{
        "id": "bus-speed-dist", "type": "lens",
        "attributes": {
            "title": "🚀 Speed Distribution",
            "visualizationType": "lnsXY",
            "state": {
                "datasourceStates": {"formBased": {"layers": {"layer1": {
                    "columnOrder": ["col_speed", "col_count"],
                    "columns": {
                        "col_speed": {
                            "label": "Speed (km/h)", "dataType": "number",
                            "operationType": "range", "sourceField": "speed",
                            "isBucketed": True, "scale": "interval",
                            "params": {
                                "type": "histogram", "ranges": [],
                                "maxBars": "auto",
                                "format": {"id": "number"},
                                "parentFormat": {"id": "range"},
                            },
                        },
                        "col_count": {
                            "label": "Count", "dataType": "number",
                            "operationType": "count", "isBucketed": False,
                            "scale": "ratio", "sourceField": "___records___",
                        },
                    },
                    "incompleteColumns": {},
                }}}},
                "visualization": {
                    "legend": {"isVisible": False},
                    "preferredSeriesType": "bar_stacked",
                    "layers": [xy_layer("col_speed", "col_count", color="#F5A700")],
                },
                "query": {"query": "", "language": "kuery"}, "filters": [],
            },
        },
        "references": REF,
    }])

    # Top routes pie
    bulk_create([{
        "id": "bus-top-routes", "type": "lens",
        "attributes": {
            "title": "🗺 Top Routes by Pings",
            "visualizationType": "lnsPie",
            "state": {
                "datasourceStates": {"formBased": {"layers": {"layer1": {
                    "columnOrder": ["col_route", "col_count"],
                    "columns": {
                        "col_route": {
                            "label": "Route", "dataType": "string",
                            "operationType": "terms", "sourceField": "route_no",
                            "isBucketed": True, "scale": "ordinal",
                            "params": {
                                "size": 12,
                                "orderBy": {"type": "column", "columnId": "col_count"},
                                "orderDirection": "desc",
                                "otherBucket": True, "missingBucket": False,
                                "parentFormat": {"id": "terms"},
                            },
                        },
                        "col_count": {
                            "label": "Pings", "dataType": "number",
                            "operationType": "count", "isBucketed": False,
                            "scale": "ratio", "sourceField": "___records___",
                        },
                    },
                    "incompleteColumns": {},
                }}}},
                "visualization": {
                    "shape": "donut",
                    "layers": [{
                        "layerId": "layer1", "layerType": "data",
                        "primaryGroups": ["col_route"], "metrics": ["col_count"],
                        "numberDisplay": "percent", "categoryDisplay": "default",
                        "legendDisplay": "default", "nestedLegend": False,
                    }],
                },
                "query": {"query": "", "language": "kuery"}, "filters": [],
            },
        },
        "references": REF,
    }])

    # Vehicle trajectory table
    bulk_create([{
        "id": "bus-trajectory-table", "type": "lens",
        "attributes": {
            "title": "🛣 Vehicle Trajectory",
            "visualizationType": "lnsDatatable",
            "state": {
                "datasourceStates": {"formBased": {"layers": {"layer1": {
                    "columnOrder": [
                        "col_vehicle", "col_route_id", "col_route_no", "col_route_name",
                        "col_pings", "col_avg_speed", "col_max_speed", "col_last_seen",
                    ],
                    "columns": {
                        "col_vehicle": {
                            "label": "Vehicle ID", "dataType": "string",
                            "operationType": "terms", "sourceField": "vehicle",
                            "isBucketed": True, "scale": "ordinal",
                            "params": {
                                "size": 20,
                                "orderBy": {"type": "column", "columnId": "col_pings"},
                                "orderDirection": "desc",
                                "otherBucket": False, "missingBucket": False,
                                "parentFormat": {"id": "terms"},
                            },
                        },
                        "col_route_id": {
                            "label": "Route ID", "dataType": "string",
                            "operationType": "terms", "sourceField": "route_id",
                            "isBucketed": True, "scale": "ordinal",
                            "params": {
                                "size": 1,
                                "orderBy": {"type": "alphabetical", "fallback": False},
                                "orderDirection": "asc",
                                "otherBucket": False, "missingBucket": True,
                                "parentFormat": {"id": "terms"},
                            },
                        },
                        "col_route_no": {
                            "label": "Tuyến", "dataType": "string",
                            "operationType": "terms", "sourceField": "route_no",
                            "isBucketed": True, "scale": "ordinal",
                            "params": {
                                "size": 1,
                                "orderBy": {"type": "alphabetical", "fallback": False},
                                "orderDirection": "asc",
                                "otherBucket": False, "missingBucket": True,
                                "parentFormat": {"id": "terms"},
                            },
                        },
                        "col_route_name": {
                            "label": "Tên tuyến", "dataType": "string",
                            "operationType": "terms",
                            "sourceField": "route_name.keyword",
                            "isBucketed": True, "scale": "ordinal",
                            "params": {
                                "size": 1,
                                "orderBy": {"type": "alphabetical", "fallback": False},
                                "orderDirection": "asc",
                                "otherBucket": False, "missingBucket": True,
                                "parentFormat": {"id": "terms"},
                            },
                        },
                        "col_pings": {
                            "label": "GPS Pings", "dataType": "number",
                            "operationType": "count", "isBucketed": False,
                            "scale": "ratio", "sourceField": "___records___",
                        },
                        "col_avg_speed": {
                            "label": "Tốc độ TB (km/h)", "dataType": "number",
                            "operationType": "average", "sourceField": "speed",
                            "isBucketed": False, "scale": "ratio",
                            "params": {"format": {"id": "number", "params": {"decimals": 1}}},
                        },
                        "col_max_speed": {
                            "label": "Tốc độ Max", "dataType": "number",
                            "operationType": "max", "sourceField": "speed",
                            "isBucketed": False, "scale": "ratio",
                            "params": {"format": {"id": "number", "params": {"decimals": 0}}},
                        },
                        "col_last_seen": {
                            "label": "Last seen", "dataType": "date",
                            "operationType": "last_value", "sourceField": "@timestamp",
                            "isBucketed": False, "scale": "ratio",
                            "params": {
                                "sortField": "@timestamp", "showArrayValues": False,
                                "format": {"id": "date", "params": {"pattern": "HH:mm:ss"}},
                            },
                        },
                    },
                    "incompleteColumns": {},
                }}}},
                "visualization": {
                    "columns": [
                        {"columnId": "col_vehicle",    "isTransposed": False, "width": 190},
                        {"columnId": "col_route_id",   "isTransposed": False, "width": 85},
                        {"columnId": "col_route_no",   "isTransposed": False, "width": 70},
                        {"columnId": "col_route_name", "isTransposed": False, "width": 230},
                        {"columnId": "col_pings",      "isTransposed": False, "width": 100},
                        {"columnId": "col_avg_speed",  "isTransposed": False, "width": 150,
                         "colorMode": "cell",
                         "palette": {"type": "palette", "name": "temperature"}},
                        {"columnId": "col_max_speed",  "isTransposed": False, "width": 120},
                        {"columnId": "col_last_seen",  "isTransposed": False},
                    ],
                    "layerId": "layer1", "layerType": "data",
                    "rowHeight": "single", "rowHeightLines": 1,
                    "paginationSize": 20,
                    "sorting": {"columnId": "col_pings", "direction": "desc"},
                },
                "query": {"query": "", "language": "kuery"}, "filters": [],
            },
        },
        "references": REF,
    }])


# ── 4. Vega Map (bypasses EMS — uses map.tilemap.url = OSM from kibana.yml) ───
def setup_vega_map(dv_id):
    print("\n[4] Vega map (OSM — no EMS dependency)")

    # Vega spec: config.kibana.type="map" → Kibana renders OSM tiles from
    # map.tilemap.url in kibana.yml, then overlays the Vega marks
    vega_spec = {
        "$schema": "https://vega.github.io/schema/vega/v5.json",
        "config": {
            "kibana": {
                "type": "map",
                "latitude": 10.78,
                "longitude": 106.66,
                "zoom": 11,
                # False → Kibana uses map.tilemap.url (OSM) from kibana.yml instead of EMS
                "mapStyle": False,
                "delayRepaint": True,
            }
        },
        "data": [
            {
                "name": "gps",
                "url": {
                    "%context%": True,
                    "%timefield%": "@timestamp",
                    "index": INDEX,
                    "body": {
                        "size": 2000,
                        "_source": [
                            "location", "vehicle", "speed",
                            "route_no", "route_name", "@timestamp",
                        ],
                        "sort": [{"@timestamp": {"order": "desc"}}],
                    },
                },
                "format": {"property": "hits.hits"},
                "transform": [
                    {"type": "formula", "as": "lon",
                     "expr": "datum._source.location.lon"},
                    {"type": "formula", "as": "lat",
                     "expr": "datum._source.location.lat"},
                    {"type": "formula", "as": "speed",
                     "expr": "isValid(datum._source.speed) ? datum._source.speed : 0"},
                    {"type": "formula", "as": "route",
                     "expr": "datum._source.route_no || 'N/A'"},
                    {"type": "formula", "as": "route_name",
                     "expr": "datum._source.route_name || ''"},
                    {"type": "formula", "as": "v_short",
                     "expr": "slice(datum._source.vehicle || '', 0, 10) + '...'"},
                    {"type": "geopoint", "projection": "projection",
                     "fields": ["lon", "lat"]},
                ],
            }
        ],
        "scales": [
            {
                "name": "speed_color",
                "type": "linear",
                "domain": [0, 80],
                "range": ["#00B3A4", "#F5A700", "#FF0000"],
                "clamp": True,
            }
        ],
        "marks": [
            {
                "type": "symbol",
                "from": {"data": "gps"},
                "encode": {
                    "update": {
                        "x": {"field": "x"},
                        "y": {"field": "y"},
                        "size": {"value": 55},
                        "shape": {"value": "circle"},
                        "fill": {"scale": "speed_color", "field": "speed"},
                        "fillOpacity": {"value": 0.8},
                        "stroke": {"value": "white"},
                        "strokeWidth": {"value": 0.5},
                        "tooltip": {
                            "signal": (
                                "{'🚌 Xe': datum.v_short, "
                                "'Tuyến': datum.route, "
                                "'Tên tuyến': datum.route_name, "
                                "'Tốc độ': datum.speed + ' km/h', "
                                "'Thời gian': datum._source['@timestamp']}"
                            ),
                        },
                    }
                },
            }
        ],
    }

    create("visualization", "bus-vega-map", {
        "title": "🗺 Bus Positions (Live Map)",
        "visState": json.dumps({
            "title": "Bus Positions (Live Map)",
            "type": "vega",
            "aggs": [],
            "params": {"spec": json.dumps(vega_spec, ensure_ascii=False)},
        }),
        "uiStateJSON": "{}",
        "description": "OSM map via Vega — no EMS dependency",
        "kibanaSavedObjectMeta": {
            "searchSourceJSON": json.dumps({
                "index": dv_id,
                "query": {"query": "", "language": "kuery"},
                "filter": [],
            }),
        },
    }, references=[
        {"id": dv_id,
         "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
         "type": "index-pattern"},
    ])


# ── 5. Density Heatmap Map (Kibana Maps — Basic license compatible) ───────────
def setup_density_map(dv_id):
    """
    Creates a Kibana Maps saved object with:
      - OSM tilemap base layer
      - Heatmap layer using geohash_grid aggregation (works with Basic license)
    Note: geo_line (Tracks) requires Platinum license — not used here.
    """
    import uuid

    def uid():
        return uuid.uuid4().hex[:8]

    print("\n[5] Density heatmap map (Kibana Maps)")

    base_layer = {
        "id": uid(),
        "label": "Base Map (OSM)",
        "minZoom": 0,
        "maxZoom": 24,
        "alpha": 1,
        "visible": True,
        "style": {"type": "TILE"},
        "type": "TILE",
        "sourceDescriptor": {
            "type": "KIBANA_TILEMAP",
        },
    }

    heatmap_layer = {
        "id": uid(),
        "label": "GPS Density Heatmap",
        "minZoom": 0,
        "maxZoom": 24,
        "alpha": 0.75,
        "visible": True,
        "type": "HEATMAP",
        "sourceDescriptor": {
            "type": "ES_GEO_GRID",
            "id": uid(),
            "indexPatternId": dv_id,
            "geoField": "location",
            "requestType": "heatmap",
            "metrics": [{"type": "count"}],
        },
        "style": {
            "type": "HEATMAP",
            "colorRampName": "Blues",
        },
    }

    map_state = {
        "zoom": 11,
        "center": {"lat": 10.78, "lon": 106.66},
        "timeFilters": {"from": "now-1h", "to": "now"},
        "query": {"language": "kuery", "query": ""},
        "filters": [],
        "refreshConfig": {"pause": False, "value": 60000},
    }

    ok = create("map", "bus-density-heatmap", {
        "title": "🌡 Bus GPS Density Heatmap",
        "description": "Heatmap of GPS ping density — OSM base, no EMS/Platinum needed",
        "mapStateJSON": json.dumps(map_state),
        "layerListJSON": json.dumps([base_layer, heatmap_layer]),
        "uiStateJSON": "{}",
        "bounds": None,
    }, references=[
        {"id": dv_id,
         "name": "indexpattern-datasource-current-indexpattern",
         "type": "index-pattern"},
    ])
    return ok


# ── 6. Dashboard ──────────────────────────────────────────────────────────────
def setup_dashboard():
    print("\n[6] Dashboard")
    create("dashboard", "smart-bus-dashboard", {
        "title": "🚌 Smart Bus GPS — Real-time Dashboard",
        "description": "Real-time ingestion | Geospatial | Density | Time-based | Trajectory",
        "panelsJSON": json.dumps([
            # Row 1: metrics + time histogram
            {"version": "8.15.0", "type": "visualization", "gridData": {"x": 0,  "y": 0,  "w": 10, "h": 8,  "i": "p1"}, "panelIndex": "p1", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p1"},
            {"version": "8.15.0", "type": "visualization", "gridData": {"x": 10, "y": 0,  "w": 10, "h": 8,  "i": "p2"}, "panelIndex": "p2", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p2"},
            {"version": "8.15.0", "type": "lens",          "gridData": {"x": 20, "y": 0,  "w": 28, "h": 8,  "i": "p3"}, "panelIndex": "p3", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p3"},
            # Row 2: live map + charts
            {"version": "8.15.0", "type": "visualization", "gridData": {"x": 0,  "y": 8,  "w": 32, "h": 24, "i": "p4"}, "panelIndex": "p4", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p4"},
            {"version": "8.15.0", "type": "lens",          "gridData": {"x": 32, "y": 8,  "w": 16, "h": 12, "i": "p5"}, "panelIndex": "p5", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p5"},
            {"version": "8.15.0", "type": "lens",          "gridData": {"x": 32, "y": 20, "w": 16, "h": 12, "i": "p6"}, "panelIndex": "p6", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p6"},
            # Row 3: density heatmap (full width)
            {"version": "8.15.0", "type": "map",           "gridData": {"x": 0,  "y": 32, "w": 48, "h": 20, "i": "p8"}, "panelIndex": "p8", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p8"},
            # Row 4: trajectory table
            {"version": "8.15.0", "type": "lens",          "gridData": {"x": 0,  "y": 52, "w": 48, "h": 16, "i": "p7"}, "panelIndex": "p7", "embeddableConfig": {"enhancements": {}}, "panelRefName": "panel_p7"},
        ]),
        "optionsJSON": json.dumps({
            "useMargins": True, "syncColors": False,
            "syncCursor": True, "syncTooltips": False, "hidePanelTitles": False,
        }),
        "timeRestore": True,
        "timeTo": "now",
        "timeFrom": "now-1h",
        "refreshInterval": {"pause": False, "value": 5000},
        "kibanaSavedObjectMeta": {
            "searchSourceJSON": json.dumps({
                "query": {"query": "", "language": "kuery"}, "filter": [],
            }),
        },
    }, references=[
        {"id": "bus-metric-total",     "name": "panel_p1", "type": "visualization"},
        {"id": "bus-metric-vehicles",  "name": "panel_p2", "type": "visualization"},
        {"id": "bus-histogram-time",   "name": "panel_p3", "type": "lens"},
        {"id": "bus-vega-map",         "name": "panel_p4", "type": "visualization"},
        {"id": "bus-speed-dist",       "name": "panel_p5", "type": "lens"},
        {"id": "bus-top-routes",       "name": "panel_p6", "type": "lens"},
        {"id": "bus-density-heatmap",  "name": "panel_p8", "type": "map"},
        {"id": "bus-trajectory-table", "name": "panel_p7", "type": "lens"},
    ])


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Kibana Setup — Smart Bus GPS")
    print(f"  Kibana : {KIBANA}")
    print(f"  Index  : {INDEX}")
    print("=" * 55)

    wait_for_kibana()
    dv_id = setup_data_view()
    setup_metrics(dv_id)
    setup_lens(dv_id)
    setup_vega_map(dv_id)
    setup_density_map(dv_id)
    setup_dashboard()

    print("\n" + "=" * 55)
    print("  Done!")
    print(f"  Dashboard: {KIBANA}/app/dashboards#/view/smart-bus-dashboard")
    print("=" * 55)


if __name__ == "__main__":
    main()
