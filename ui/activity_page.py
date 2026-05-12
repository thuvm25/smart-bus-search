"""
Smart Bus GPS — "Activity" page.

Two sections:
  1) Most-active buses in the last 5 minutes — ranked table + map of latest
     positions, colored by speed.
  2) Track a single bus's route over the last hour — PathLayer with
     start/end markers, plus distance and speed summary.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import pydeck as pdk
import streamlit as st


ApiGet = Callable[[str, Optional[Dict]], Optional[Any]]
SpeedColor = Callable[[float], List[int]]


WINDOW_PRESETS: List[Dict[str, Any]] = [
    {"label": "1 phút",  "from": "now-1m",  "minutes": 1},
    {"label": "5 phút",  "from": "now-5m",  "minutes": 5},
    {"label": "15 phút", "from": "now-15m", "minutes": 15},
    {"label": "30 phút", "from": "now-30m", "minutes": 30},
    {"label": "1 giờ",   "from": "now-1h",  "minutes": 60},
    {"label": "3 giờ",   "from": "now-3h",  "minutes": 180},
    {"label": "6 giờ",   "from": "now-6h",  "minutes": 360},
    {"label": "Tùy chỉnh…", "from": None,   "minutes": None},
]


def _render_active_buses(api_get: ApiGet, speed_color: SpeedColor) -> List[Dict[str, Any]]:
    st.markdown(
        '<div class="section-header">🔥 Xe hoạt động nhiều nhất gần đây</div>',
        unsafe_allow_html=True,
    )

    labels = [p["label"] for p in WINDOW_PRESETS]
    c1, c2, c3 = st.columns([2, 2, 3])
    chosen_label = c1.selectbox(
        "Khoảng thời gian:",
        labels,
        index=1,  # default: 5 phút
        key="active_window_preset",
    )
    preset = next(p for p in WINDOW_PRESETS if p["label"] == chosen_label)

    if preset["from"] is None:
        custom_min = c2.number_input(
            "Số phút (tùy chỉnh):",
            min_value=1,
            max_value=24 * 60,
            value=int(st.session_state.get("active_window_custom", 10)),
            step=1,
            key="active_window_custom",
        )
        from_arg = f"now-{int(custom_min)}m"
        window_text = f"{int(custom_min)} phút"
    else:
        from_arg = preset["from"]
        window_text = preset["label"]

    size = c3.slider(
        "Số xe hiển thị:",
        min_value=3, max_value=50, value=10, step=1,
        key="active_size",
    )

    st.caption(f"⏱ Thống kê trong **{window_text}** gần nhất.")

    payload = api_get("/api/most_active_bus", {"from": from_arg, "to": "now", "size": size})
    if not payload or not payload.get("data"):
        st.info(f"Không có dữ liệu hoạt động trong {window_text} qua.")
        return []

    rows: List[Dict[str, Any]] = payload["data"]
    df = pd.DataFrame(rows)

    top = rows[0]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🥇 Xe hoạt động nhiều nhất", top["vehicle"])
    k2.metric("📡 Số ping", f"{top['pings']}")
    k3.metric("🚀 Tốc độ TB", f"{top['avg_speed']} km/h")
    k4.metric("⚡ Tốc độ tối đa", f"{top['max_speed']} km/h")

    df_map = df.copy()
    df_map["color"] = df_map["avg_speed"].apply(speed_color)
    df_map["radius"] = (df_map["pings"].clip(lower=1) ** 0.5) * 50

    scatter = pdk.Layer(
        "ScatterplotLayer",
        data=df_map,
        get_position=["lon", "lat"],
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        auto_highlight=True,
        radius_min_pixels=6,
        radius_max_pixels=24,
    )
    view_state = pdk.ViewState(
        latitude=float(df_map["lat"].mean()),
        longitude=float(df_map["lon"].mean()),
        zoom=11,
        pitch=0,
    )
    tooltip = {
        "html": (
            "<div style='font-family:Inter,sans-serif; padding:8px; background:#21262d;"
            " border-radius:8px; border:1px solid #30363d; color:#e6edf3; font-size:13px;'>"
            "<b style='color:#00b3a4'>🚌 {vehicle}</b><br>"
            "📡 Ping: <b>{pings}</b><br>"
            "🗺 Tuyến {route_no}: {route_name}<br>"
            "🚀 TB: <b>{avg_speed} km/h</b> · ⚡ Tối đa: <b>{max_speed} km/h</b><br>"
            "🕐 {timestamp}"
            "</div>"
        ),
        "style": {"backgroundColor": "transparent", "border": "none"},
    }
    st.pydeck_chart(
        pdk.Deck(layers=[scatter], initial_view_state=view_state, tooltip=tooltip, map_style=None),
        height=380,
    )

    st.dataframe(
        df[["vehicle", "pings", "avg_speed", "max_speed", "route_no", "route_name", "timestamp"]]
        .rename(columns={
            "vehicle": "Xe",
            "pings": "Số ping",
            "avg_speed": "Tốc độ TB (km/h)",
            "max_speed": "Tốc độ tối đa (km/h)",
            "route_no": "Tuyến",
            "route_name": "Tên tuyến",
            "timestamp": "Cập nhật",
        }),
        use_container_width=True,
        hide_index=True,
    )

    return rows


def _render_bus_track(api_get: ApiGet, speed_color: SpeedColor, top_rows: List[Dict[str, Any]]) -> None:
    st.markdown(
        '<div class="section-header">🛣 Hành trình xe gần đây</div>',
        unsafe_allow_html=True,
    )

    labels = [p["label"] for p in WINDOW_PRESETS]
    w1, w2 = st.columns([2, 3])
    chosen_label = w1.selectbox(
        "Khoảng thời gian:",
        labels,
        index=4,  # default: 1 giờ
        key="track_window_preset",
    )
    preset = next(p for p in WINDOW_PRESETS if p["label"] == chosen_label)

    if preset["from"] is None:
        custom_min = w2.number_input(
            "Số phút (tùy chỉnh):",
            min_value=1,
            max_value=24 * 60,
            value=int(st.session_state.get("track_window_custom", 60)),
            step=1,
            key="track_window_custom",
        )
        from_arg = f"now-{int(custom_min)}m"
        window_text = f"{int(custom_min)} phút"
    else:
        from_arg = preset["from"]
        window_text = preset["label"]

    st.caption(f"⏱ Hiển thị hành trình trong **{window_text}** gần nhất.")

    vehicle_options = [r["vehicle"] for r in top_rows if r.get("vehicle")]

    def _vehicle_label(row: Dict[str, Any]) -> str:
        veh = str(row.get("vehicle") or "")
        route_no = str(row.get("route_no") or "").strip()
        route_name = str(row.get("route_name") or "").strip()
        if route_no and route_name:
            return f"Xe {veh} — Tuyến {route_no}: {route_name}"
        if route_no:
            return f"Xe {veh} — Tuyến {route_no}"
        if route_name:
            return f"Xe {veh} — {route_name}"
        return f"Xe {veh}"

    label_by_vehicle = {
        r["vehicle"]: _vehicle_label(r)
        for r in top_rows if r.get("vehicle")
    }

    if not vehicle_options:
        st.info("Chưa có xe hoạt động trong khoảng thời gian đã chọn ở mục trên.")
        return

    vehicle = st.selectbox(
        "Chọn xe (top hoạt động):",
        vehicle_options,
        index=0,
        format_func=lambda v: label_by_vehicle.get(v, v),
        key="track_pick",
    )

    vehicle_label = label_by_vehicle.get(vehicle, vehicle)

    track = api_get("/api/bus_track", {"vehicle": vehicle, "from": from_arg, "to": "now"})
    if not track or not track.get("points"):
        st.warning(f"Không có dữ liệu hành trình cho xe **{vehicle_label}** trong {window_text} qua.")
        return

    points = track["points"]
    df_pts = pd.DataFrame(points)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📍 Số điểm", f"{track['count']}")
    k2.metric("📏 Quãng đường", f"{track['total_distance_m'] / 1000:.2f} km")
    k3.metric("🚀 Tốc độ TB", f"{track['avg_speed']} km/h")
    k4.metric("⚡ Tốc độ tối đa", f"{track['max_speed']} km/h")

    if track.get("route_no") or track.get("route_name"):
        st.caption(f"🗺 Tuyến **{track.get('route_no', '')}** — {track.get('route_name', '')}")

    path_coords = [[p["lon"], p["lat"]] for p in points]
    path_layer = pdk.Layer(
        "PathLayer",
        data=[{"path": path_coords, "name": vehicle_label}],
        get_path="path",
        get_color=[0, 179, 164, 220],
        get_width=5,
        width_min_pixels=3,
        pickable=False,
    )

    df_pts["color"] = df_pts["speed"].apply(speed_color)
    df_pts["label"] = f"📍 {vehicle_label}"
    pings_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_pts,
        get_position=["lon", "lat"],
        get_fill_color="color",
        get_radius=20,
        pickable=True,
        radius_min_pixels=2,
        radius_max_pixels=6,
    )

    start = points[0]
    end = points[-1]
    endpoints = pd.DataFrame([
        {"lat": start["lat"], "lon": start["lon"], "label": "🟢 Bắt đầu",
         "speed": start.get("speed", 0), "timestamp": start.get("timestamp", ""),
         "color": [34, 197, 94, 240]},
        {"lat": end["lat"], "lon": end["lon"], "label": "🔴 Hiện tại",
         "speed": end.get("speed", 0), "timestamp": end.get("timestamp", ""),
         "color": [239, 68, 68, 240]},
    ])
    endpoint_layer = pdk.Layer(
        "ScatterplotLayer",
        data=endpoints,
        get_position=["lon", "lat"],
        get_fill_color="color",
        get_line_color=[255, 255, 255, 255],
        line_width_min_pixels=2,
        get_radius=60,
        radius_min_pixels=8,
        radius_max_pixels=14,
        stroked=True,
        pickable=True,
    )

    view_state = pdk.ViewState(
        latitude=float(df_pts["lat"].mean()),
        longitude=float(df_pts["lon"].mean()),
        zoom=12,
        pitch=0,
    )

    tooltip = {
        "html": (
            "<div style='font-family:Inter,sans-serif; padding:8px; background:#21262d;"
            " border-radius:8px; border:1px solid #30363d; color:#e6edf3; font-size:13px;'>"
            "<b style='color:#00b3a4'>{label}</b>"
            "🚀 <b>{speed} km/h</b><br>"
            "🕐 {timestamp}"
            "</div>"
        ),
        "style": {"backgroundColor": "transparent", "border": "none"},
    }

    st.pydeck_chart(
        pdk.Deck(
            layers=[path_layer, pings_layer, endpoint_layer],
            initial_view_state=view_state,
            tooltip=tooltip,
            map_style=None,
        ),
        height=460,
    )

    with st.expander("📋 Chi tiết các điểm GPS"):
        st.dataframe(
            df_pts[["timestamp", "lat", "lon", "speed", "heading"]]
            .rename(columns={
                "timestamp": "Thời gian",
                "lat": "Vĩ độ",
                "lon": "Kinh độ",
                "speed": "Tốc độ (km/h)",
                "heading": "Hướng",
            }),
            use_container_width=True,
            hide_index=True,
        )


def render_activity_page(api_get: ApiGet, speed_color: SpeedColor) -> None:
    st.markdown(
        "<h1 style='color:#0f172a; font-size:2rem; font-weight:800; margin-bottom:0'>"
        "📊 Smart Bus GPS — Hoạt động & Hành trình xe</h1>",
        unsafe_allow_html=True,
    )

    top_rows = _render_active_buses(api_get, speed_color)
    _render_bus_track(api_get, speed_color, top_rows)
