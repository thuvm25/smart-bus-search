"""
Create a proper Kibana Maps saved object for Smart Bus live tracking.

Fixes:
  1. Creates the missing 'smart-bus-live-map' map (URL was pointing to nonexistent object)
  2. Adds Tracks layer (geo_line aggregation) to draw bus route lines like Google Maps

Layers:
  - Base Map (OSM tilemap — no EMS dependency)
  - Bus GPS Points (ES Documents, colored by speed)
  - Bus Routes Tracks (ES GeoLine per vehicle — draws movement paths)

Usage:
  source scripts/.venv/bin/activate
  python scripts/setup_kibana_map.py
"""

import json
import os
import sys
import time
import uuid

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

KIBANA  = os.getenv("KIBANA_HOST", "http://localhost:5601")
INDEX   = os.getenv("ES_INDEX",    "bus_waypoints")
DV_ID   = os.getenv("DV_ID",       "bus_waypoints_dv")
MAP_ID  = "smart-bus-live-map"
HEADERS = {"kbn-xsrf": "true", "Content-Type": "application/json"}

OSM_URL = "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"


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


def ensure_data_view():
    """Create data view if it doesn't exist yet."""
    r = requests.get(
        f"{KIBANA}/api/data_views/data_view/{DV_ID}",
        headers=HEADERS, timeout=10,
    )
    if r.status_code == 200:
        print(f"  Data view '{DV_ID}' already exists.")
        return
    print(f"  Creating data view '{DV_ID}'...")
    r = requests.post(
        f"{KIBANA}/api/data_views/data_view",
        headers=HEADERS,
        json={
            "data_view": {
                "id": DV_ID,
                "title": INDEX,
                "timeFieldName": "@timestamp",
                "name": "Smart Bus GPS",
            },
            "override": True,
        },
        timeout=15,
    )
    if r.status_code in (200, 201):
        print(f"  Data view created: {DV_ID}")
    else:
        print(f"  WARN: data view creation returned {r.status_code}: {r.text[:200]}")


def uid():
    return uuid.uuid4().hex[:8]


# ── layer definitions ─────────────────────────────────────────────────────────
def base_map_layer():
    """OSM tilemap base layer — no EMS dependency."""
    return {
        "id": uid(),
        "label": "Base Map (OSM)",
        "minZoom": 0,
        "maxZoom": 24,
        "alpha": 1,
        "visible": True,
        "type": "RASTER_TILE",
        "sourceDescriptor": {
            "type": "KIBANA_TILEMAP",
        },
    }


def gps_points_layer():
    """
    ES Documents layer — plots each GPS ping as a circle colored by speed.
    Green (slow) → Yellow → Red (fast).
    """
    return {
        "id": uid(),
        "label": "Bus GPS Points",
        "minZoom": 0,
        "maxZoom": 24,
        "alpha": 0.8,
        "visible": True,
        "type": "GEOJSON_VECTOR",
        "sourceDescriptor": {
            "type": "ES_SEARCH",
            "id": uid(),
            "indexPatternId": DV_ID,
            "geoField": "location",
            "limit": 2048,
            "filterByMapBounds": True,
            "tooltipProperties": [
                "vehicle", "route_no", "route_name", "speed", "@timestamp",
            ],
            "sortField": "@timestamp",
            "sortOrder": "DESC",
            "scalingType": "TOP_HITS",
            "topHitsSplitField": "vehicle",
            "topHitsSize": 1,
        },
        "style": {
            "type": "VECTOR",
            "properties": {
                # Color dots by speed: green → yellow → red
                "fillColor": {
                    "type": "DYNAMIC",
                    "options": {
                        "field": {
                            "name": "speed",
                            "origin": "source",
                        },
                        "color": "Green to Red",
                        "fieldMetaOptions": {
                            "isEnabled": True,
                            "sigma": 3,
                        },
                    },
                },
                "lineColor": {
                    "type": "STATIC",
                    "options": {"color": "#FFFFFF"},
                },
                "lineWidth": {
                    "type": "STATIC",
                    "options": {"size": 1},
                },
                "iconSize": {
                    "type": "STATIC",
                    "options": {"size": 6},
                },
                "symbolizeAs": {
                    "options": {"value": "circle"},
                },
                "labelText": {
                    "type": "STATIC",
                    "options": {"value": ""},
                },
            },
            "isTimeAware": True,
        },
    }


def heatmap_layer():
    """
    Heatmap layer using geohash_grid aggregation.
    Works with Basic license (geo_line/Tracks requires Platinum — not used).
    Shows GPS ping density: yellow (low) → red (high).
    colorRampName uses Kibana built-in palette names (no spaces, no extra fields).
    """
    return {
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
            "indexPatternId": DV_ID,
            "geoField": "location",
            "requestType": "heatmap",
            "metrics": [{"type": "count"}],
        },
        "style": {
            "type": "HEATMAP",
            "colorRampName": "Blues",
        },
    }


# ── create map ────────────────────────────────────────────────────────────────
def create_map():
    print(f"\nCreating Kibana Maps object: {MAP_ID}")

    layer_list = [
        base_map_layer(),
        heatmap_layer(),    # density heatmap (Basic license compatible)
        gps_points_layer(), # individual GPS dots on top
    ]

    map_state = {
        "zoom": 11,
        "center": {"lat": 10.78, "lon": 106.66},
        "timeFilters": {"from": "now-1h", "to": "now"},
        "query": {"language": "kuery", "query": ""},
        "filters": [],
        "refreshConfig": {"pause": False, "value": 60000},
    }

    attributes = {
        "title": "Smart Bus Live Map",
        "description": "Real-time bus positions and route tracks (OSM base, no EMS)",
        "mapStateJSON": json.dumps(map_state),
        "layerListJSON": json.dumps(layer_list),
        "uiStateJSON": "{}",
        "bounds": None,
    }

    references = [
        {
            "id": DV_ID,
            "name": "indexpattern-datasource-current-indexpattern",
            "type": "index-pattern",
        }
    ]

    r = requests.post(
        f"{KIBANA}/api/saved_objects/map/{MAP_ID}?overwrite=true",
        headers=HEADERS,
        json={"attributes": attributes, "references": references},
        timeout=15,
    )

    if r.status_code in (200, 201):
        print(f"  OK — map/{MAP_ID} created.")
        print(f"\n  Open map: {KIBANA}/app/maps/map/{MAP_ID}")
    else:
        print(f"  FAIL ({r.status_code}): {r.text[:300]}")
        sys.exit(1)


# ── kibana.yml check ──────────────────────────────────────────────────────────
def check_kibana_tilemap():
    """
    Verify Kibana Maps tilemap config is set so OSM base map works.
    The kibana.yml must have:
      map.includeElasticMapsService: false
      map.tilemap.url: "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
    """
    yml_path = os.path.join(
        os.path.dirname(__file__), "..", "kibana", "kibana.yml"
    )
    yml_path = os.path.normpath(yml_path)
    if not os.path.exists(yml_path):
        print(f"  WARN: kibana.yml not found at {yml_path}")
        return
    with open(yml_path) as f:
        content = f.read()
    if "map.tilemap.url" in content:
        print(f"  kibana.yml: tilemap URL is configured (OSM base map should work).")
    else:
        print(
            f"  WARN: map.tilemap.url not set in kibana.yml!\n"
            f"  Add these lines to {yml_path}:\n"
            f"    map.includeElasticMapsService: false\n"
            f"    map.tilemap.url: \"{OSM_URL}\"\n"
            f"  Then restart the kibana container."
        )


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Kibana Maps Setup — Smart Bus Live Map")
    print(f"  Kibana  : {KIBANA}")
    print(f"  Index   : {INDEX}")
    print(f"  Map ID  : {MAP_ID}")
    print("=" * 55)

    wait_for_kibana()
    check_kibana_tilemap()
    ensure_data_view()
    create_map()

    print("\n" + "=" * 55)
    print("  Done! Layers created:")
    print("    Base Map (OSM)       — tilemap, no EMS")
    print("    GPS Density Heatmap  — geohash_grid, Basic license OK")
    print("    Bus GPS Points       — individual pings colored by speed")
    print("  NOTE: geo_line (Tracks) requires Platinum license — using Heatmap instead")
    print("=" * 55)


if __name__ == "__main__":
    main()
