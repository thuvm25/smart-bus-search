"""
Smart Bus GPS — "Nearby" page.

Renders a map + tables for buses (and approximate stops) within a chosen
radius of a (lat, lon). Uses the FastAPI backend's `/api/nearby_buses` and
`/api/nearby_stops` endpoints.

`render_nearby_page(api_get, speed_color)` is the entry point — `api_get`
and `speed_color` are injected from the host script so this module stays
free of project-wide helpers.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import pydeck as pdk
import streamlit as st

try:
    from streamlit_js_eval import get_geolocation
except ImportError:
    get_geolocation = None


ApiGet = Callable[[str, Optional[Dict]], Optional[Any]]
SpeedColor = Callable[[float], List[int]]


def circle_polygon(lat: float, lon: float, radius_m: float, sides: int = 64) -> List[List[float]]:
    """Approximate a geodesic circle as a polygon ring of (lon, lat) pairs."""
    R = 6378137.0
    coords: List[List[float]] = []
    for i in range(sides):
        ang = 2 * math.pi * i / sides
        dlat_deg = math.degrees((radius_m * math.cos(ang)) / R)
        dlon_deg = math.degrees(
            (radius_m * math.sin(ang)) / (R * math.cos(math.radians(lat)))
        )
        coords.append([lon + dlon_deg, lat + dlat_deg])
    coords.append(coords[0])
    return coords


def _handle_geolocation() -> None:
    """Process a pending location request from the browser, if any."""
    if not st.session_state.get("_loc_pending") or get_geolocation is None:
        return

    loc = get_geolocation()
    if loc and isinstance(loc, dict) and loc.get("coords"):
        coords = loc["coords"]
        try:
            st.session_state["nb_lat"] = float(coords.get("latitude"))
            st.session_state["nb_lon"] = float(coords.get("longitude"))
            st.session_state["_loc_pending"] = False
            st.session_state["_loc_ok"] = True
            st.rerun()
        except (TypeError, ValueError):
            st.session_state["_loc_pending"] = False
            st.session_state["_loc_err"] = "Không đọc được tọa độ từ trình duyệt."


def _location_controls() -> None:
    """Render the 'use my location' button + status row."""
    btn_col, cancel_col, info_col = st.columns([1, 1, 3])
    loc_disabled = get_geolocation is None
    pending = bool(st.session_state.get("_loc_pending"))

    if btn_col.button(
        "📍 Dùng vị trí của tôi",
        disabled=loc_disabled or pending,
        help=("Cần cài đặt streamlit-js-eval" if loc_disabled else "Trình duyệt sẽ hỏi quyền truy cập vị trí"),
    ):
        st.session_state["_loc_pending"] = True
        st.session_state.pop("_loc_err", None)
        st.session_state.pop("_loc_ok", None)
        st.rerun()

    if pending and cancel_col.button("❌ Hủy", help="Dừng chờ vị trí trình duyệt"):
        st.session_state["_loc_pending"] = False
        st.rerun()

    if pending:
        info_col.info("⏳ Đang lấy vị trí — hãy chấp nhận quyền truy cập trên trình duyệt (chỉ hoạt động với HTTPS hoặc localhost).")
    elif st.session_state.get("_loc_ok"):
        info_col.success(f"Đã dùng vị trí trình duyệt: ({st.session_state['nb_lat']:.5f}, {st.session_state['nb_lon']:.5f})")
    elif st.session_state.get("_loc_err"):
        info_col.error(st.session_state["_loc_err"])


def render_nearby_page(api_get: ApiGet, speed_color: SpeedColor) -> None:
    st.markdown('<div class="section-header">📌 Tìm xe buýt / trạm gần bạn</div>', unsafe_allow_html=True)

    # Seed defaults so the geolocation handler can write to them before the
    # number_input widgets are instantiated.
    st.session_state.setdefault("nb_lat", 10.7769)
    st.session_state.setdefault("nb_lon", 106.7009)

    _handle_geolocation()
    _location_controls()

    c1, c2, c3, c4 = st.columns([2, 2, 3, 2])
    nb_lat = c1.number_input("Vĩ độ (lat)", format="%.6f", step=0.0001, key="nb_lat")
    nb_lon = c2.number_input("Kinh độ (lon)", format="%.6f", step=0.0001, key="nb_lon")
    nb_radius = c3.slider("Bán kính (m)", min_value=100, max_value=3000, value=500, step=50, key="nb_radius")
    show_stops = c4.checkbox("Hiển thị trạm (heuristic)", value=True, key="nb_show_stops")

    st.caption(
        "💡 Mặc định là Bến Thành (10.7769, 106.7009). Bấm \"📍 Dùng vị trí của tôi\" để dùng GPS trình duyệt, "
        "hoặc nhập tọa độ thủ công."
    )

    bus_data = api_get(
        "/api/nearby_buses",
        {"lat": nb_lat, "lon": nb_lon, "radius_m": nb_radius, "from": "now-1h", "to": "now+3h", "max_vehicles": 500},
    )
    stop_data = (
        api_get(
            "/api/nearby_stops",
            {"lat": nb_lat, "lon": nb_lon, "radius_m": nb_radius, "from": "now-1h", "to": "now+3h"},
        )
        if show_stops
        else None
    )

    layers = [
        pdk.Layer(
            "PolygonLayer",
            data=[{"polygon": circle_polygon(nb_lat, nb_lon, nb_radius)}],
            get_polygon="polygon",
            get_fill_color=[0, 179, 164, 25],
            get_line_color=[0, 179, 164, 220],
            line_width_min_pixels=2,
            pickable=False,
            stroked=True,
            filled=True,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=[{"lat": nb_lat, "lon": nb_lon}],
            get_position=["lon", "lat"],
            get_fill_color=[59, 130, 246, 240],
            get_line_color=[255, 255, 255, 255],
            line_width_min_pixels=2,
            get_radius=20,
            radius_min_pixels=8,
            radius_max_pixels=14,
            stroked=True,
            pickable=False,
        ),
    ]

    bus_count = 0
    df_bus = pd.DataFrame()
    if bus_data and bus_data.get("features"):
        bus_rows = []
        for f in bus_data["features"]:
            p = f["properties"]
            bus_rows.append({
                "vehicle":    p.get("vehicle", ""),
                "route_no":   p.get("route_no", ""),
                "route_name": p.get("route_name", ""),
                "speed":      p.get("speed", 0) or 0,
                "lat":        p["lat"],
                "lon":        p["lon"],
                "distance_m": p.get("distance_m", 0),
                "timestamp":  p.get("timestamp", ""),
            })
        df_bus = pd.DataFrame(bus_rows)
        df_bus["color"] = df_bus["speed"].apply(speed_color)
        bus_count = len(df_bus)

        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=df_bus,
                get_position=["lon", "lat"],
                get_fill_color="color",
                get_radius=70,
                pickable=True,
                auto_highlight=True,
                radius_min_pixels=4,
                radius_max_pixels=14,
            )
        )

    stop_count = 0
    df_stops = pd.DataFrame()
    if stop_data and stop_data.get("features"):
        stop_rows = []
        for f in stop_data["features"]:
            p = f["properties"]
            stop_rows.append({
                "lat":        p["lat"],
                "lon":        p["lon"],
                "pings":      p.get("pings", 0),
                "vehicles":   p.get("vehicles", 0),
                "routes":     ", ".join(p.get("routes", []) or []),
                "distance_m": p.get("distance_m", 0),
            })
        df_stops = pd.DataFrame(stop_rows)
        stop_count = len(df_stops)
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=df_stops,
                get_position=["lon", "lat"],
                get_fill_color=[168, 85, 247, 220],
                get_line_color=[255, 255, 255, 255],
                line_width_min_pixels=1,
                get_radius=40,
                radius_min_pixels=5,
                radius_max_pixels=12,
                stroked=True,
                pickable=True,
            )
        )

    zoom_level = max(11.0, 17.0 - math.log2(max(nb_radius, 50) / 50.0))
    view_state = pdk.ViewState(latitude=nb_lat, longitude=nb_lon, zoom=zoom_level, pitch=0)

    tooltip = {
        "html": (
            "<div style='font-family:Inter,sans-serif; padding:8px; background:#21262d;"
            " border-radius:8px; border:1px solid #30363d; color:#e6edf3; font-size:13px;'>"
            "<b style='color:#00b3a4'>🚌 {vehicle}</b><br>"
            "🗺 Tuyến {route_no}: {route_name}<br>"
            "🚀 Tốc độ: <b>{speed} km/h</b><br>"
            "📏 Khoảng cách: <b>{distance_m} m</b><br>"
            "🕐 {timestamp}"
            "</div>"
        ),
        "style": {"backgroundColor": "transparent", "border": "none"},
    }

    st.pydeck_chart(
        pdk.Deck(layers=layers, initial_view_state=view_state, tooltip=tooltip, map_style=None),
        height=460,
    )

    cap_bits = [f"📍 ({nb_lat:.5f}, {nb_lon:.5f})", f"🎯 {nb_radius} m", f"🚌 {bus_count} xe"]
    if show_stops:
        cap_bits.append(f"🚏 {stop_count} cụm trạm")
    st.caption(" · ".join(cap_bits))

    tab_bus, tab_stop = st.tabs(["🚌 Xe trong bán kính", "🚏 Trạm trong bán kính"])
    with tab_bus:
        if not df_bus.empty:
            st.dataframe(
                df_bus[["distance_m", "vehicle", "route_no", "route_name", "speed", "timestamp", "lat", "lon"]]
                .rename(columns={
                    "distance_m": "Khoảng cách (m)",
                    "vehicle": "Xe",
                    "route_no": "Tuyến",
                    "route_name": "Tên tuyến",
                    "speed": "Tốc độ (km/h)",
                    "timestamp": "Cập nhật",
                    "lat": "Vĩ độ",
                    "lon": "Kinh độ",
                }),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Không có xe trong bán kính đã chọn.")

    with tab_stop:
        if show_stops and not df_stops.empty:
            st.dataframe(
                df_stops[["distance_m", "vehicles", "pings", "routes", "lat", "lon"]]
                .rename(columns={
                    "distance_m": "Khoảng cách (m)",
                    "vehicles": "Số xe",
                    "pings": "Số lượt dừng",
                    "routes": "Tuyến đi qua",
                    "lat": "Vĩ độ",
                    "lon": "Kinh độ",
                }),
                use_container_width=True,
                hide_index=True,
            )
        elif not show_stops:
            st.info("Bật ô \"Hiển thị trạm\" ở trên để xem các cụm trạm gần đây.")
        else:
            st.info("Chưa phát hiện cụm trạm nào trong bán kính.")
