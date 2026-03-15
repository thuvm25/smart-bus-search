import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="HCMC Bus GPS Search", layout="wide")

import math

import pandas as pd
import pydeck as pdk
import requests

from api_client import (
    get_analytics_active_count,
    get_analytics_density,
    get_analytics_speed,
    get_analytics_stats,
    run_benchmark,
    search_active,
    search_nearby,
    search_vehicle_trace,
)

st.title("HCMC Bus Visual Search")
st.caption("Visual demo for bus movement, nearest stops, and route labels")

LIGHT_MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
BUS_ICON_URL = "https://img.icons8.com/color/96/bus.png"


def _speed_band(speed: float | None) -> str:
    if speed is None:
        return "Unknown"
    if speed > 50:
        return ">50 km/h"
    if speed >= 40:
        return "40-50 km/h"
    if speed >= 30:
        return "30-40 km/h"
    if speed >= 20:
        return "20-30 km/h"
    return "<20 km/h"


def _speed_color(speed: float | None) -> list[int]:
    if speed is None:
        return [130, 130, 130]
    if speed > 50:
        return [220, 40, 40]  # red
    if speed >= 40:
        return [245, 190, 55]  # yellow
    if speed >= 30:
        return [40, 130, 210]  # blue
    if speed >= 20:
        return [130, 130, 130]  # gray
    return [15, 15, 15]  # black


def _make_circle_polygon(lat: float, lon: float, radius_m: int, points: int = 72) -> list[list[float]]:
    """Approximate a meter-based circle around center as [lon, lat] polygon."""
    lat_rad = math.radians(lat)
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = max(111_320.0 * math.cos(lat_rad), 1e-6)

    polygon: list[list[float]] = []
    for i in range(points + 1):
        theta = 2.0 * math.pi * i / points
        d_lat = (radius_m * math.sin(theta)) / meters_per_deg_lat
        d_lon = (radius_m * math.cos(theta)) / meters_per_deg_lon
        polygon.append([lon + d_lon, lat + d_lat])
    return polygon


def _zoom_for_radius(radius_m: int, lat: float) -> float:
    """Pick a map zoom so the nearby search circle is comfortably visible."""
    if radius_m <= 200:
        base_zoom = 15.5
    elif radius_m <= 400:
        base_zoom = 14.8
    elif radius_m <= 700:
        base_zoom = 14.2
    elif radius_m <= 1000:
        base_zoom = 13.8
    elif radius_m <= 1500:
        base_zoom = 13.3
    elif radius_m <= 2200:
        base_zoom = 12.9
    else:
        base_zoom = 12.5

    # Slight latitude compensation to keep circle sizing more consistent.
    lat_factor = max(0.85, min(1.1, math.cos(math.radians(lat)) / 0.95))
    return max(10.5, min(16.5, base_zoom + (lat_factor - 1.0) * 0.8))


def _normalize_items(mode_name: str, payload: dict) -> pd.DataFrame:
    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not items:
        return pd.DataFrame()

    df = pd.DataFrame(items)

    # Nearby endpoint returns x/y for lon/lat.
    if mode_name == "Nearby buses":
        if "x" in df.columns and "lon" not in df.columns:
            df["lon"] = df["x"]
        if "y" in df.columns and "lat" not in df.columns:
            df["lat"] = df["y"]

    # Vehicle trace has route metadata at top-level payload.
    if mode_name == "Vehicle trace" and isinstance(payload, dict):
        for key in ["vehicle", "mapping_route_no", "mapping_route_id", "route_name"]:
            if key in payload and key not in df.columns:
                df[key] = payload.get(key)

    return df


def _render_result_panel(mode_name: str, payload: dict, df: pd.DataFrame) -> None:
    st.subheader("Ket qua tim")
    st.metric("So ban ghi", int(len(df)))
    if mode_name == "Nearby buses":
        total = int(payload.get("total", len(df)))
        returned = int(payload.get("returned", len(df)))
        limit = int(payload.get("limit", returned))
        st.write(f"Tim thay trong ban kinh: **{total}**")
        st.write(f"Dang hien thi: **{returned}** (gioi han toi da **{limit}**) ")
    if mode_name == "Vehicle trace" and not df.empty:
        first = df.iloc[0].to_dict()
        route_label = first.get("route_name") or "N/A"
        stop_label = first.get("stop_name") or "N/A"
        st.write(f"Vehicle: `{first.get('vehicle', 'N/A')}`")
        st.write(f"Route: **{route_label}**")
        st.write(f"Diem dung gan nhat: **{stop_label}**")
    elif not df.empty:
        top_stops = (
            df["stop_name"].dropna().value_counts().head(3).index.tolist()
            if "stop_name" in df.columns
            else []
        )
        if top_stops:
            st.write("Top stop_name xuat hien:")
            for name in top_stops:
                st.write(f"- {name}")


def _render_points_map(
    df: pd.DataFrame,
    center_lat: float | None = None,
    center_lon: float | None = None,
    radius_m: int | None = None,
) -> None:
    map_center_lat = float(center_lat) if center_lat is not None else float(df["lat"].mean())
    map_center_lon = float(center_lon) if center_lon is not None else float(df["lon"].mean())
    zoom = _zoom_for_radius(int(radius_m), map_center_lat) if radius_m is not None else 11

    view_state = pdk.ViewState(
        latitude=map_center_lat,
        longitude=map_center_lon,
        zoom=zoom,
        pitch=0,
    )
    layers = []

    icon_df = df.copy()
    icon_df["icon_data"] = [
        {
            "url": BUS_ICON_URL,
            "width": 96,
            "height": 96,
            "anchorY": 96,
        }
    ] * len(icon_df)

    bus_icon_layer = pdk.Layer(
        "IconLayer",
        data=icon_df,
        get_icon="icon_data",
        get_position="[lon, lat]",
        get_size=4,
        size_scale=8,
        size_min_pixels=22,
        pickable=True,
    )
    layers.append(bus_icon_layer)

    bus_shadow_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_fill_color=[50, 90, 160, 90],
        get_radius=16,
        pickable=False,
        opacity=0.5,
    )
    layers.append(bus_shadow_layer)

    if center_lat is not None and center_lon is not None:
        center_layer = pdk.Layer(
            "ScatterplotLayer",
            data=[{"lat": center_lat, "lon": center_lon}],
            get_position="[lon, lat]",
            get_fill_color=[220, 20, 60],
            get_radius=70,
            pickable=True,
            opacity=0.95,
        )
        layers.append(center_layer)

    if center_lat is not None and center_lon is not None and radius_m is not None:
        circle_polygon = _make_circle_polygon(float(center_lat), float(center_lon), int(radius_m))
        radius_layer = pdk.Layer(
            "PolygonLayer",
            data=[{"polygon": circle_polygon}],
            get_polygon="polygon",
            get_fill_color=[65, 105, 225, 30],
            get_line_color=[65, 105, 225, 220],
            line_width_min_pixels=2,
            stroked=True,
            filled=True,
            pickable=False,
        )
        layers.append(radius_layer)

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style=LIGHT_MAP_STYLE,
        tooltip={"text": "Vehicle: {vehicle}\nRoute: {route_name}\nStop: {stop_name}\nSpeed: {speed}"},
    )
    st.pydeck_chart(deck, use_container_width=True)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in meters between two points."""
    r = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _render_trace_map(df: pd.DataFrame) -> None:
    if len(df) < 2:
        _render_points_map(df)
        return

    segments: list[dict] = []
    ordered = df.copy()
    if "datetime" in ordered.columns:
        ordered["datetime"] = pd.to_datetime(ordered["datetime"], errors="coerce")
        # Drop rows with invalid datetime so order is meaningful
        ordered = ordered.dropna(subset=["datetime"])
        ordered = ordered.sort_values("datetime")
    ordered = ordered.reset_index(drop=True)

    if len(ordered) < 2:
        _render_points_map(ordered)
        return

    # Downsample for display when too many points (avoid dense wedge)
    max_points = 1500
    if len(ordered) > max_points:
        step = len(ordered) // max_points
        ordered = ordered.iloc[:: max(1, step)].reset_index(drop=True)

    # Only draw segment if consecutive in time and not a huge jump (avoid "fly" lines between trips)
    max_time_gap_minutes = 30.0
    max_distance_m = 2000.0

    for i in range(len(ordered) - 1):
        a = ordered.iloc[i]
        b = ordered.iloc[i + 1]
        if pd.isna(a["lat"]) or pd.isna(a["lon"]) or pd.isna(b["lat"]) or pd.isna(b["lon"]):
            continue
        lat_a, lon_a = float(a["lat"]), float(a["lon"])
        lat_b, lon_b = float(b["lat"]), float(b["lon"])
        dist_m = _haversine_m(lat_a, lon_a, lat_b, lon_b)
        if dist_m > max_distance_m:
            continue
        if "datetime" in ordered.columns and not (pd.isna(a["datetime"]) or pd.isna(b["datetime"])):
            delta = (b["datetime"] - a["datetime"]).total_seconds() / 60.0
            if delta > max_time_gap_minutes or delta < 0:
                continue
        speed_val = a.get("speed")
        segments.append(
            {
                "path": [[lon_a, lat_a], [lon_b, lat_b]],
                "color": _speed_color(speed_val),
                "speed_band": _speed_band(speed_val),
                "speed": speed_val,
            }
        )

    point_layer = pdk.Layer(
        "ScatterplotLayer",
        data=ordered,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius=8,
        pickable=True,
    )
    path_layer = pdk.Layer(
        "PathLayer",
        data=segments,
        get_path="path",
        get_color="color",
        width_min_pixels=2,
        pickable=True,
    )

    view_state = pdk.ViewState(
        latitude=float(ordered["lat"].mean()),
        longitude=float(ordered["lon"].mean()),
        zoom=12,
        pitch=25,
    )

    deck = pdk.Deck(
        layers=[path_layer, point_layer],
        initial_view_state=view_state,
        map_style=LIGHT_MAP_STYLE,
        tooltip={"text": "Speed band: {speed_band}\nSpeed: {speed}"},
    )
    st.pydeck_chart(deck, use_container_width=True)


st.sidebar.header("Search Options")
mode = st.sidebar.selectbox("Choose search type", ["Active buses", "Nearby buses", "Vehicle trace"])

# Auto-refresh control (for Active / Nearby modes, Search tab only)
auto_refresh_sec = st.sidebar.slider("Auto refresh (seconds, 0 = off)", 0, 10, 0)

payload: dict | None = None

if mode == "Active buses":
    minutes = st.sidebar.slider("Active in last (minutes, 0 = all time)", 0, 60, 0)
    manual_click = st.sidebar.button("Search now")
    if auto_refresh_sec > 0 or manual_click:
        with st.spinner("Fetching active buses..."):
            payload = search_active(minutes)

elif mode == "Nearby buses":
    lat = st.sidebar.number_input("Latitude", value=10.7769, format="%.6f")
    lon = st.sidebar.number_input("Longitude", value=106.7009, format="%.6f")
    radius_m = st.sidebar.slider("Radius (meters)", 100, 3000, 700, step=100)
    nearby_limit = st.sidebar.slider("Max records", 100, 2000, 1000, step=100)
    manual_click = st.sidebar.button("Search now")
    if auto_refresh_sec > 0 or manual_click:
        with st.spinner("Searching nearby buses..."):
            payload = search_nearby(lat, lon, radius_m, nearby_limit)

elif mode == "Vehicle trace":
    vehicle_id = st.sidebar.text_input("Vehicle ID", "e738d8470a8d11a7a6d3dd7741f295c0dc3fd6779ed9d76ea7325fd1ee277891")
    minutes = st.sidebar.slider("Trace minutes (0 = full history)", 0, 120, 0)
    if st.sidebar.button("Search"):
        with st.spinner("Fetching vehicle trace..."):
            payload = search_vehicle_trace(vehicle_id, minutes)

tab_search, tab_analysis, tab_benchmark = st.tabs(["Search", "Analysis", "Benchmark"])

with tab_search:
    # Only auto-refresh when user is on Search tab and using Active/Nearby modes
    if auto_refresh_sec > 0 and mode in ["Active buses", "Nearby buses"]:
        st_autorefresh(interval=auto_refresh_sec * 1000, key="auto_refresh_counter")

    if payload:
        df = _normalize_items(mode, payload)

        if df.empty:
            st.warning("Khong co ket qua hop le de visualize.")
        else:
            if "speed" not in df.columns:
                df["speed"] = None
            df["color"] = df["speed"].apply(_speed_color)
            if "route_name" not in df.columns:
                df["route_name"] = None
            if "stop_name" not in df.columns:
                df["stop_name"] = None
            if "vehicle" not in df.columns:
                df["vehicle"] = None

            _render_result_panel(mode, payload, df)

            st.subheader("Ban do")
            if "lat" in df.columns and "lon" in df.columns:
                if mode == "Vehicle trace":
                    _render_trace_map(df)
                elif mode == "Nearby buses":
                    _render_points_map(
                        df,
                        center_lat=float(payload.get("lat", lat if "lat" in locals() else df["lat"].mean())),
                        center_lon=float(payload.get("lon", lon if "lon" in locals() else df["lon"].mean())),
                        radius_m=int(payload.get("radius_m", radius_m if "radius_m" in locals() else 500)),
                    )
                else:
                    _render_points_map(df)
            else:
                st.warning("Response khong co cot lat/lon de ve ban do.")

            st.subheader("Bang du lieu")
            show_cols = [
                c
                for c in [
                    "vehicle",
                    "datetime",
                    "speed",
                    "ignition",
                    "route_name",
                    "stop_name",
                    "mapping_route_no",
                    "lat",
                    "lon",
                ]
                if c in df.columns
            ]
            st.dataframe(df[show_cols], use_container_width=True)
    else:
        st.info("Run a search from the sidebar to see visualization.")

with tab_analysis:
    st.subheader("Analytics")
    try:
        stats = get_analytics_stats()
        st.metric("Index doc count", stats.get("doc_count", "N/A"))
        st.json(stats)
    except Exception as e:
        st.warning(f"Could not load stats: {e}")

    minutes_analytics = st.slider("Time window (minutes)", 1, 60, 5, key="analytics_min")
    try:
        active = get_analytics_active_count(minutes=minutes_analytics)
        st.metric("Active vehicles (last N min)", active.get("count", "N/A"))
    except Exception as e:
        st.warning(f"Could not load active count: {e}")

    try:
        speed_stats = get_analytics_speed(minutes=minutes_analytics)
        st.write("Speed statistics:")
        st.json(speed_stats)
    except Exception as e:
        st.warning(f"Could not load speed stats: {e}")

    try:
        density = get_analytics_density(precision=5, minutes=minutes_analytics)
        st.write("Density (geohash grid):")
        st.json(density)
    except Exception as e:
        st.warning(f"Could not load density: {e}")

with tab_benchmark:
    st.subheader("Benchmark")
    st.caption("Benchmark dùng dữ liệu synthetic (không cần simulator). Có thể mất 1–2 phút.")
    st.caption("Để có dữ liệu xe bus trên bản đồ (Search), chạy simulator riêng: docker compose up -d simulator")
    if st.button("Run benchmark"):
        with st.spinner("Đang chạy benchmark (indexing, search, aggregation)... Có thể mất 1–2 phút."):
            try:
                result = run_benchmark()
                st.success("Benchmark hoàn tất.")
                st.write("**Indexing:**")
                st.json(result.get("indexing", {}))
                st.write("**Search latency (ms):**")
                st.json(result.get("search_latency", {}))
                st.write("**Aggregation latency (ms):**")
                st.json(result.get("aggregation_latency", {}))
                st.write("**Scalability:**")
                st.json(result.get("scalability", []))
            except requests.exceptions.Timeout:
                st.error("Benchmark timeout (request > 2 phút). Backend hoặc ES có thể đang quá tải.")
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    st.error("Benchmark API không tìm thấy (404). Rebuild backend image rồi chạy lại: docker compose build backend && docker compose up -d backend")
                else:
                    st.error(f"Benchmark failed: {e}")
            except Exception as e:
                st.error(f"Benchmark failed: {e}")
    else:
        st.info("Bấm 'Run benchmark' để chạy đánh giá hiệu năng (cần backend + Elasticsearch).")