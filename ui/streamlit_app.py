import streamlit as st

st.set_page_config(page_title="HCMC Bus GPS Search", layout="wide")

import math

import pandas as pd
import pydeck as pdk

from api_client import (
    search_active,
    search_nearby,
    search_vehicle_trace,
)

st.title("HCMC Bus Visual Search")
st.caption("Visual demo for bus movement, nearest stops, and route labels")

LIGHT_MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"


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
    col_a, col_b = st.columns([2.2, 1.2])

    with col_a:
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

    with col_b:
        st.markdown("Speed legend")
        st.write("- Red: >50 km/h")
        st.write("- Yellow: 40-50 km/h")
        st.write("- Blue: 30-40 km/h")
        st.write("- Gray: 20-30 km/h")
        st.write("- Black: <20 km/h")


def _render_points_map(
    df: pd.DataFrame,
    center_lat: float | None = None,
    center_lon: float | None = None,
    radius_m: int | None = None,
) -> None:
    map_center_lat = float(center_lat) if center_lat is not None else float(df["lat"].mean())
    map_center_lon = float(center_lon) if center_lon is not None else float(df["lon"].mean())

    view_state = pdk.ViewState(
        latitude=map_center_lat,
        longitude=map_center_lon,
        zoom=11,
        pitch=0,
    )
    layers = []

    point_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius=35,
        pickable=True,
        opacity=0.85,
    )
    layers.append(point_layer)

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


def _render_trace_map(df: pd.DataFrame) -> None:
    if len(df) < 2:
        _render_points_map(df)
        return

    segments: list[dict] = []
    ordered = df.copy()
    if "datetime" in ordered.columns:
        ordered["datetime"] = pd.to_datetime(ordered["datetime"], errors="coerce")
        ordered = ordered.sort_values("datetime")
    ordered = ordered.reset_index(drop=True)

    for i in range(len(ordered) - 1):
        a = ordered.iloc[i]
        b = ordered.iloc[i + 1]
        if pd.isna(a["lat"]) or pd.isna(a["lon"]) or pd.isna(b["lat"]) or pd.isna(b["lon"]):
            continue
        speed_val = a.get("speed")
        segments.append(
            {
                "path": [[float(a["lon"]), float(a["lat"])], [float(b["lon"]), float(b["lat"])]] ,
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
        get_radius=40,
        pickable=True,
    )
    path_layer = pdk.Layer(
        "PathLayer",
        data=segments,
        get_path="path",
        get_color="color",
        width_min_pixels=4,
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
payload: dict | None = None

if mode == "Active buses":
    minutes = st.sidebar.slider("Active in last (minutes)", 1, 60, 10)
    if st.sidebar.button("Search"):
        with st.spinner("Fetching active buses..."):
            payload = search_active(minutes)

elif mode == "Nearby buses":
    lat = st.sidebar.number_input("Latitude", value=10.7769, format="%.6f")
    lon = st.sidebar.number_input("Longitude", value=106.7009, format="%.6f")
    radius_m = st.sidebar.slider("Radius (meters)", 100, 3000, 700, step=100)
    nearby_limit = st.sidebar.slider("Max records", 100, 2000, 1000, step=100)
    if st.sidebar.button("Search"):
        with st.spinner("Searching nearby buses..."):
            payload = search_nearby(lat, lon, radius_m, nearby_limit)

elif mode == "Vehicle trace":
    vehicle_id = st.sidebar.text_input("Vehicle ID", "e738d8470a8d11a7a6d3dd7741f295c0dc3fd6779ed9d76ea7325fd1ee277891")
    minutes = st.sidebar.slider("Trace minutes", 1, 120, 30)
    if st.sidebar.button("Search"):
        with st.spinner("Fetching vehicle trace..."):
            payload = search_vehicle_trace(vehicle_id, minutes)

if payload:
    df = _normalize_items(mode, payload)

    if df.empty:
        st.warning("Khong co ket qua hop le de visualize.")
    else:
        # Prepare visualization columns.
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