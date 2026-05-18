"""
Smart Bus GPS — "Dashboard" page.

Comprehensive real-time dashboard:
  - Fuzzy route search + plate filter + advanced filters
  - Live map (auto-refresh) with route detail panel
  - Aggregation stats panel (top routes, jam %, pings_per_min, speed_by_hour…)
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import pydeck as pdk
import streamlit as st
from st_keyup import st_keyup

from nearby_page import _handle_geolocation, _location_controls, circle_polygon


ApiGet = Callable[[str, Optional[Dict]], Optional[Any]]
SpeedColor = Callable[[float], List[int]]


# ── Session state defaults ────────────────────────────────────────────────────
DEFAULTS = {
    "selected_route_no":   "",
    "selected_route_name": "",
    "selected_plate_no":   "",
    # Bộ lọc nâng cao — feed thẳng vào bool.filter của /api/livebus + /api/stats
    "filter_window":       "now-1h",
    "filter_ignition":     "—",
    "filter_speed_min":    0,
    "filter_speed_max":    80,
    # "Tìm gần một điểm" mode — overrides /api/livebus với /api/nearby_buses
    "nb_enabled":          False,
    "nb_lat":              10.7769,
    "nb_lon":              106.7009,
    "nb_radius":           500,
    "nb_show_stops":       True,
}


def _chart_label(title: str, help_text: str, took_ms: int = 0) -> None:
    """Render chart label dùng st.markdown(help=...) để có (?) icon
    + tooltip Streamlit native — giống hệt st.metric."""
    took_suffix = (f" <span style='color:#64748b; font-weight:400; "
                   f"font-size:0.85em; margin-left:8px'>"
                   f"{took_ms} ms</span>") if took_ms else ""
    st.markdown(
        f"**{title}**{took_suffix}",
        unsafe_allow_html=True,
        help=help_text,
    )


def _render_route_card(route: Dict) -> None:
    """Render route detail dạng card đơn giản."""
    rows = [
        ("Mã tuyến",       route.get("route_no", "")),
        ("Tên tuyến",      route.get("route_name", "")),
        ("Mô tả",          route.get("description", "")),
        ("Loại tuyến",     route.get("route_type", "")),
        ("Giá vé",         route.get("fare", "")),
        ("Độ dài",         route.get("length", "")),
        ("Thời gian chạy", route.get("schedule", "")),
        ("Giãn cách",      route.get("frequency", "")),
        ("Đơn vị",         route.get("operator", "")),
    ]
    html = "<div class='route-info-card'>"
    for label, val in rows:
        if val:
            html += f"<div class='row'><b>{label}:</b> {val}</div>"
    fwd = route.get("stops_forward") or []
    rtn = route.get("stops_return") or []
    if fwd:
        html += (f"<div class='row'><b>Lượt đi ({len(fwd)} trạm):</b> "
                 f"{' → '.join(fwd[:6])}{' …' if len(fwd) > 6 else ''}</div>")
    if rtn:
        html += (f"<div class='row'><b>Lượt về ({len(rtn)} trạm):</b> "
                 f"{' → '.join(rtn[:6])}{' …' if len(rtn) > 6 else ''}</div>")
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def _build_livebus_params() -> Dict:
    """Gom tất cả filter từ session_state thành tham số /api/livebus."""
    p: Dict = {
        "from": st.session_state["filter_window"],
        "to":   "now+3h",
        "max_vehicles": 500,
    }
    if st.session_state.get("selected_route_no"):
        p["route_no"] = st.session_state["selected_route_no"]
    if st.session_state.get("selected_plate_no"):
        p["plate_no"] = st.session_state["selected_plate_no"]

    ign = st.session_state.get("filter_ignition", "—")
    if ign == "Đang nổ máy":
        p["ignition"] = "true"
    elif ign == "Đã tắt máy":
        p["ignition"] = "false"

    s_min = st.session_state.get("filter_speed_min", 0)
    s_max = st.session_state.get("filter_speed_max", 80)
    if s_min > 0:
        p["speed_gte"] = s_min
    if s_max < 120:
        p["speed_lt"] = s_max
    return p


def _build_stats_params() -> Dict:
    """Filter dimension áp lên /api/stats — đồng bộ với Live Map."""
    p: Dict = {
        "from": st.session_state["filter_window"],
        "to":   "now",
    }
    if st.session_state.get("selected_route_no"):
        p["route_no"] = st.session_state["selected_route_no"]
    if st.session_state.get("selected_plate_no"):
        p["plate_no"] = st.session_state["selected_plate_no"]

    ign = st.session_state.get("filter_ignition", "—")
    if ign == "Đang nổ máy":
        p["ignition"] = "true"
    elif ign == "Đã tắt máy":
        p["ignition"] = "false"

    s_min = st.session_state.get("filter_speed_min", 0)
    s_max = st.session_state.get("filter_speed_max", 80)
    if s_min > 0:
        p["speed_gte"] = s_min
    if s_max < 120:
        p["speed_lt"] = s_max
    return p


def _filter_summary() -> str:
    """Render gọn các filter đang áp dụng để hiện trên caption."""
    _window_labels = {
        "now-15m": "15 phút qua",
        "now-30m": "30 phút qua",
        "now-1h":  "1 giờ qua",
        "now-3h":  "3 giờ qua",
        "now-24h": "24 giờ qua",
    }
    win = st.session_state["filter_window"]
    parts: list = [f"`{_window_labels.get(win, win)}`"]
    if st.session_state.get("selected_route_no"):
        parts.append(f"tuyến=`{st.session_state['selected_route_no']}`")
    if st.session_state.get("selected_plate_no"):
        parts.append(f"biển số=`{st.session_state['selected_plate_no']}`")
    ign = st.session_state.get("filter_ignition", "—")
    if ign != "—":
        parts.append(f"nổ máy=`{ign}`")
    s_min = st.session_state.get("filter_speed_min", 0)
    s_max = st.session_state.get("filter_speed_max", 80)
    if s_min > 0 or s_max < 120:
        parts.append(f"tốc độ=`{s_min}–{s_max}`")
    return " · ".join(parts)


def render_dashboard_page(api_get: ApiGet, speed_color: SpeedColor) -> None:
    # ── Init session state ────────────────────────────────────────────────────
    for key, val in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        "<h1 style='color:#0f172a; font-size:2rem; font-weight:800; margin-bottom:0'>"
        "🚌 Smart Bus GPS — Real-time Dashboard</h1>",
        unsafe_allow_html=True,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # Hàng 1 — Search tuyến + lọc biển số
    # ══════════════════════════════════════════════════════════════════════════
    col_route, col_plate = st.columns([3, 2])

    with col_route:
        st.markdown('<div class="section-header">🔍 Tìm kiếm Tuyến xe</div>',
                    unsafe_allow_html=True)
        search_term = st_keyup(
            "search",
            placeholder="VD: Chợ Rẫy, tuyến 05, Bến Thành...",
            label_visibility="collapsed",
            debounce=300,
        )

    with col_plate:
        st.markdown('<div class="section-header">🚘 Lọc theo Biển số xe</div>',
                    unsafe_allow_html=True)
        plate_data = api_get("/api/platesearch",
                             {"route_no": st.session_state["selected_route_no"]})
        plate_options = ["— Tất cả xe —"]
        plate_label_map: Dict[str, str] = {"— Tất cả xe —": ""}
        if plate_data and plate_data.get("data"):
            for d in plate_data["data"]:
                pno = d.get("plate_no", "")
                if pno:
                    plate_options.append(pno)
                    plate_label_map[pno] = pno

        current_plate = st.session_state["selected_plate_no"]
        default_idx = (plate_options.index(current_plate)
                       if current_plate in plate_options else 0)

        selected_label = st.selectbox(
            "plate_select",
            options=plate_options,
            index=default_idx,
            label_visibility="collapsed",
        )
        new_plate = plate_label_map.get(selected_label, "")
        if new_plate != st.session_state["selected_plate_no"]:
            st.session_state["selected_plate_no"] = new_plate
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # Search results as cards
    # ══════════════════════════════════════════════════════════════════════════
    if search_term and search_term.strip() and not st.session_state["selected_route_no"]:
        search_data = api_get("/api/fuzzysearch", {"q": search_term, "size": 10})
        if search_data and search_data.get("data"):
            total = search_data["total"]
            shown = len(search_data["data"])
            suffix = f" (hiển thị {shown})" if total > shown else ""
            st.markdown(
                f"<div class='result-count'>{total} tuyến tìm thấy{suffix}</div>",
                unsafe_allow_html=True,
            )
            for r in search_data["data"]:
                route_no   = r.get("route_no", "")
                route_name = r.get("route_name", "")
                stop       = r.get("matched_stop", "")
                color = ("green" if route_no == st.session_state["selected_route_no"]
                         else "blue")
                card_label = (
                    f":{color}[**{route_no}**]   {route_name}"
                    + (f"\n\n:gray[📍 *{stop}*]" if stop else "")
                )
                if st.button(card_label, key=f"sel_{route_no}",
                             use_container_width=True):
                    st.session_state["selected_route_no"]   = route_no
                    st.session_state["selected_route_name"] = route_name
                    st.session_state["selected_plate_no"]  = ""
                    st.rerun()
        elif search_data is not None:
            st.info(f"Không tìm thấy tuyến nào phù hợp với: **{search_term}**")

    # ══════════════════════════════════════════════════════════════════════════
    # Selected route banner + clear button
    # ══════════════════════════════════════════════════════════════════════════
    selected_no   = st.session_state["selected_route_no"]
    selected_name = st.session_state["selected_route_name"]
    if selected_no:
        col_banner, col_clear = st.columns([7, 1])
        with col_banner:
            st.markdown(
                f"<div class='selected-banner'>🗺 Đang lọc: <b>Tuyến {selected_no}</b>"
                + (f" — {selected_name}" if selected_name else "") + "</div>",
                unsafe_allow_html=True,
            )
        with col_clear:
            if st.button("✕ Bỏ lọc", use_container_width=True):
                st.session_state["selected_route_no"] = ""
                st.session_state["selected_route_name"] = ""
                st.session_state["selected_plate_no"] = ""
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # Hàng 2 — Bộ lọc nâng cao (luôn hiển thị, không wrap expander)
    # ══════════════════════════════════════════════════════════════════════════
    fc1, fc2, fc3, fc4 = st.columns([1, 1, 2, 0.6])

    with fc1:
        _window_options = ["now-15m", "now-30m", "now-1h", "now-3h", "now-24h"]
        _window_labels = {
            "now-15m": "15 phút qua",
            "now-30m": "30 phút qua",
            "now-1h":  "1 giờ qua",
            "now-3h":  "3 giờ qua",
            "now-24h": "24 giờ qua",
        }
        st.session_state["filter_window"] = st.selectbox(
            "Cửa sổ thời gian",
            options=_window_options,
            index=_window_options.index(st.session_state["filter_window"]),
            format_func=lambda v: _window_labels.get(v, v),
            help="Áp mệnh đề `range` lên @timestamp",
        )

    with fc2:
        st.session_state["filter_ignition"] = st.selectbox(
            "Trạng thái nổ máy",
            options=["—", "Đang nổ máy", "Đã tắt máy"],
            index=["—", "Đang nổ máy", "Đã tắt máy"].index(
                st.session_state["filter_ignition"]),
            help="Áp mệnh đề `term` lên trường `ignition` (boolean)",
        )

    with fc3:
        speed_min, speed_max = st.slider(
            "Khoảng tốc độ (km/h)",
            min_value=0, max_value=120,
            value=(st.session_state["filter_speed_min"],
                   st.session_state["filter_speed_max"]),
            help="Áp mệnh đề `range` lên trường `speed`",
        )
        st.session_state["filter_speed_min"] = speed_min
        st.session_state["filter_speed_max"] = speed_max

    with fc4:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("✕ Xoá", key="clear_advanced", use_container_width=True):
            st.session_state["filter_window"]    = "now-1h"
            st.session_state["filter_ignition"]  = "—"
            st.session_state["filter_speed_min"] = 0
            st.session_state["filter_speed_max"] = 80
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # Hàng 3 — "Tìm gần một điểm" (gộp từ trang Tìm gần tôi)
    # ══════════════════════════════════════════════════════════════════════════
    def _on_nb_toggle() -> None:
        # When the radius-filter toggle flips ON, auto-request GPS so the user
        # doesn't have to click "Dùng vị trí của tôi" separately.
        if st.session_state.get("nb_enabled"):
            st.session_state["_loc_pending"] = True
            st.session_state.pop("_loc_err", None)
            st.session_state.pop("_loc_ok", None)

    nb_on = st.toggle(
        "Bật chế độ lọc theo bán kính",
        key="nb_enabled",
        on_change=_on_nb_toggle,
        help="Khi bật, bản đồ chỉ hiện xe (và tuỳ chọn cụm trạm) trong bán kính "
             "quanh điểm chọn. Các bộ lọc tuyến/biển số/nổ máy/tốc độ/cửa sổ "
             "vẫn áp dụng song song. Tự động lấy vị trí trình duyệt khi bật.",
    )
    if nb_on:
        _handle_geolocation()
        _location_controls()
        nc1, nc2, nc3, nc4 = st.columns([2, 2, 3, 2])
        nc1.number_input("Vĩ độ (lat)", format="%.6f", step=0.0001, key="nb_lat")
        nc2.number_input("Kinh độ (lon)", format="%.6f", step=0.0001, key="nb_lon")
        nc3.slider("Bán kính (m)", min_value=100, max_value=3000,
                   step=50, key="nb_radius")
        nc4.checkbox("Hiển thị cụm trạm", key="nb_show_stops")
        st.caption(
            "💡 Tự động lấy vị trí trình duyệt khi bật. Nếu bị từ chối, "
            "mặc định Bến Thành (10.7769, 106.7009) — có thể bấm "
            "\"📍 Dùng vị trí của tôi\" để thử lại."
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Live map + route detail (2 cột)
    # ══════════════════════════════════════════════════════════════════════════
    col_map, col_info = st.columns([3, 2])

    with col_map:
        # Selectbox chọn chu kỳ auto-refresh (đặt ngoài fragment để re-định nghĩa
        # fragment với run_every mới mỗi khi đổi giá trị)
        _, sel_col = st.columns([7, 2])
        with sel_col:
            interval_label = st.selectbox(
                "Tự làm mới",
                options=["Tắt", "5 giây", "10 giây", "30 giây", "60 giây"],
                index=1,
                label_visibility="collapsed",
                key="map_refresh_interval",
            )
        _interval_map = {"Tắt": None, "5 giây": 5, "10 giây": 10,
                         "30 giây": 30, "60 giây": 60}
        _refresh_sec = _interval_map[interval_label]

        @st.fragment(run_every=f"{_refresh_sec}s" if _refresh_sec else None)
        def render_live_map():
            last_refresh = pd.Timestamp.now().strftime("%H:%M:%S")
            suffix = (f" · tự làm mới {_refresh_sec}s" if _refresh_sec
                      else " · không tự làm mới")
            nb_on = bool(st.session_state.get("nb_enabled"))
            st.caption(f"🕐 Cập nhật lần cuối: **{last_refresh}**{suffix}")
            filter_parts = _filter_summary()
            if nb_on:
                filter_parts += f" · bán kính=`{st.session_state['nb_radius']} m`"
            st.caption(f"🔎 Bộ lọc: {filter_parts}")

            if nb_on:
                nb_lat = float(st.session_state["nb_lat"])
                nb_lon = float(st.session_state["nb_lon"])
                nb_r   = int(st.session_state["nb_radius"])
                # Reuse livebus filter set + add radius params
                params_pos = _build_livebus_params()
                params_pos.update({"lat": nb_lat, "lon": nb_lon, "radius_m": nb_r})
                pos_data = api_get("/api/nearby_buses", params_pos)
            else:
                params_pos = _build_livebus_params()
                pos_data = api_get("/api/livebus", params_pos)

            features = (pos_data.get("features") if pos_data else None) or []

            if not features and not nb_on:
                st.info("Không có dữ liệu vị trí xe khớp bộ lọc.")
                return

            count = (pos_data.get("count", len(features)) if pos_data else 0)

            if nb_on:
                k1, k2 = st.columns(2)
                k1.metric("Xe khớp", f"{count}")
                k2.metric("Bán kính", f"{st.session_state['nb_radius']} m")
            else:
                st.metric("Xe khớp", f"{count}")

            points = []
            for f in features:
                p = f["properties"]
                points.append({
                    "lat":        p["lat"],
                    "lon":        p["lon"],
                    "speed":      p.get("speed", 0) or 0,
                    "vehicle":    p.get("vehicle", ""),
                    "route_no":   p.get("route_no", ""),
                    "route_name": p.get("route_name", ""),
                    "plate_no":   p.get("plate_no", "") or p.get("vehicle", ""),
                    "timestamp":  p.get("timestamp", ""),
                    "distance_m": p.get("distance_m", 0),
                })
            df_pos = pd.DataFrame(points)
            if not df_pos.empty:
                df_pos["color"] = df_pos["speed"].apply(speed_color)

            layers: List[pdk.Layer] = []

            if nb_on:
                # Circle (behind) + center marker (above buses)
                layers.append(pdk.Layer(
                    "PolygonLayer",
                    data=[{"polygon": circle_polygon(nb_lat, nb_lon, nb_r)}],
                    get_polygon="polygon",
                    get_fill_color=[0, 179, 164, 25],
                    get_line_color=[0, 179, 164, 220],
                    line_width_min_pixels=2,
                    pickable=False, stroked=True, filled=True,
                ))

            if not df_pos.empty:
                layers.append(pdk.Layer(
                    "ScatterplotLayer",
                    data=df_pos,
                    get_position=["lon", "lat"],
                    get_fill_color="color",
                    get_radius=80,
                    pickable=True,
                    auto_highlight=True,
                    radius_min_pixels=4,
                    radius_max_pixels=16,
                ))

            if nb_on and st.session_state.get("nb_show_stops"):
                stop_data = api_get("/api/nearby_stops", {
                    "lat": nb_lat, "lon": nb_lon, "radius_m": nb_r,
                    "from": st.session_state["filter_window"], "to": "now+3h",
                })
                if stop_data and stop_data.get("features"):
                    stop_rows = [{
                        "lat":        sf["properties"]["lat"],
                        "lon":        sf["properties"]["lon"],
                        "pings":      sf["properties"].get("pings", 0),
                        "vehicles":   sf["properties"].get("vehicles", 0),
                        "routes":     ", ".join(sf["properties"].get("routes") or []),
                        "distance_m": sf["properties"].get("distance_m", 0),
                    } for sf in stop_data["features"]]
                    layers.append(pdk.Layer(
                        "ScatterplotLayer",
                        data=stop_rows,
                        get_position=["lon", "lat"],
                        get_fill_color=[168, 85, 247, 220],
                        get_line_color=[255, 255, 255, 255],
                        line_width_min_pixels=1,
                        get_radius=40,
                        radius_min_pixels=5, radius_max_pixels=12,
                        stroked=True, pickable=True,
                    ))

            if nb_on:
                # Center marker on top
                layers.append(pdk.Layer(
                    "ScatterplotLayer",
                    data=[{"lat": nb_lat, "lon": nb_lon}],
                    get_position=["lon", "lat"],
                    get_fill_color=[59, 130, 246, 240],
                    get_line_color=[255, 255, 255, 255],
                    line_width_min_pixels=2,
                    get_radius=20,
                    radius_min_pixels=8, radius_max_pixels=14,
                    stroked=True, pickable=False,
                ))
                zoom = max(11.0, 17.0 - math.log2(max(nb_r, 50) / 50.0))
                view_state = pdk.ViewState(latitude=nb_lat, longitude=nb_lon,
                                           zoom=zoom, pitch=0)
            else:
                view_state = pdk.ViewState(latitude=10.78, longitude=106.66,
                                           zoom=11, pitch=0)

            tooltip_html = """
                <div style='font-family:Inter,sans-serif; padding:8px;
                            background:#ffffff; border-radius:8px;
                            border:1px solid #d6d6d2; color:#0f172a;
                            font-size:13px;
                            box-shadow:0 4px 16px rgba(15,23,42,0.12);'>
                    <b style='color:#0d9488'>🚌 {plate_no}</b><br>
                    🗺 Tuyến {route_no}: {route_name}<br>
                    🚀 Tốc độ: <b>{speed} km/h</b><br>
            """
            if nb_on:
                tooltip_html += "📏 Cách: <b>{distance_m} m</b><br>"
            tooltip_html += "🕐 {timestamp}</div>"
            tooltip = {
                "html": tooltip_html,
                "style": {"backgroundColor": "transparent", "border": "none"},
            }

            st.pydeck_chart(
                pdk.Deck(layers=layers, initial_view_state=view_state,
                         tooltip=tooltip,
                         map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"),
                height=460,
            )
            st.caption("Màu chấm: 🟢 chậm → 🔴 nhanh"
                       + (" · 🟣 cụm trạm · 🔵 điểm trung tâm" if nb_on else ""))

        render_live_map()

    with col_info:
        st.markdown('<div class="section-header">🗺 Thông tin Tuyến xe</div>',
                    unsafe_allow_html=True)
        route_no_filter = st.session_state.get("selected_route_no", "")
        detail_data = api_get(
            "/api/routedetail",
            {"route_no": route_no_filter} if route_no_filter else {},
        )
        routes = detail_data.get("data", []) if detail_data else []

        with st.container(height=560, border=False):
            if not routes:
                st.info("Chọn tuyến từ ô tìm kiếm để xem chi tiết.")
            elif route_no_filter:
                _render_route_card(routes[0])
            else:
                for route in routes[:20]:
                    with st.expander(
                        f"Tuyến {route.get('route_no','')} — "
                        f"{route.get('route_name','')}"
                    ):
                        _render_route_card(route)

    # ══════════════════════════════════════════════════════════════════════════
    # Aggregation panel — /api/stats (manual refresh, không auto-refresh)
    # ══════════════════════════════════════════════════════════════════════════
    @st.fragment
    def render_stats():
        head_col, btn_col = st.columns([8, 1.2])
        with head_col:
            st.markdown('<div class="section-header">📊 Thống kê tổng hợp</div>',
                        unsafe_allow_html=True)
        with btn_col:
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            st.button("🔄 Làm mới", key="refresh_stats",
                      use_container_width=True)

        base_params = _build_stats_params()
        last_refresh = pd.Timestamp.now().strftime("%H:%M:%S")
        st.caption(f"🕐 Cập nhật lần cuối: **{last_refresh}** · {_filter_summary()}")

        # ── Hàng KPI 1: tổng quan vận hành ─────────────────────────────────
        kpi_data = api_get("/api/stats", {**base_params, "metric": "vehicles_active"})
        jam_data = api_get("/api/stats", {**base_params, "metric": "traffic_jam"})

        if kpi_data and kpi_data.get("data"):
            d = kpi_data["data"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(
                "Xe đang hoạt động",
                f"{d['vehicles_active']:,}",
                help="Số xe DUY NHẤT có ít nhất 1 bản ghi GPS trong cửa sổ. "
                     "Tổng hợp: cardinality(vehicle).",
            )
            c2.metric(
                "Tuyến đang chạy",
                f"{d['routes_in_use']:,}",
                help="Số tuyến DUY NHẤT có xe vận hành trong cửa sổ. "
                     "Tổng hợp: cardinality(route_no).",
            )
            if jam_data and jam_data.get("data"):
                c3.metric(
                    "Tỷ lệ kẹt xe",
                    f"{jam_data['data']['jam_pct']}%",
                    help="% bản tin GPS có vận tốc < 5 km/h trong cửa sổ. "
                         "Đại diện cho mức độ ùn tắc + dừng đèn đỏ + dừng "
                         "trạm. Tổng hợp: range(speed) chia 4 nhóm "
                         "kẹt/chậm/bình thường/nhanh rồi lấy tỷ lệ kẹt/tổng.",
                )
            else:
                c3.metric("Tỷ lệ kẹt xe", "—")
            c4.metric(
                "Thời gian",
                f"{kpi_data.get('took', 0)} ms",
                help="Thời gian Elasticsearch xử lý truy vấn (trường took). "
                     "Đo nội bộ ES, không bao gồm độ trễ mạng.",
            )
        else:
            st.warning("Backend chưa trả dữ liệu thống kê.")

        # ── Top N tuyến ────────────────────────────────────────────────────
        top_size = st.slider(
            "Số tuyến hiển thị", 3, 20, 5, step=1, key="stats_top_size",
            help="Tham số `size` của tổng hợp terms. ES sẽ trả N tuyến có "
                 "nhiều xe nhất. N nhỏ = bảng gọn; N lớn = thấy "
                 "phân bố rộng hơn.",
        )

        top_data = api_get("/api/stats", {**base_params, "metric": "top_routes",
                                          "size": top_size})
        if top_data and top_data.get("data"):
            df_top = pd.DataFrame(top_data["data"])

            cc1, cc2 = st.columns([3, 2])
            with cc1:
                _chart_label(
                    f"📊 Top {top_size} tuyến theo số xe đang vận hành",
                    f"Tổng hợp: terms(route_no) size={top_size} sắp xếp _count giảm dần, "
                    f"tổng hợp con cardinality(vehicle) lấy số xe duy nhất. "
                    f"Tuyến đông xe = tuyến hoạt động sôi nổi nhất.",
                    took_ms=top_data.get("took", 0),
                )
                chart_df = df_top.set_index("route_no")[["vehicles"]]
                st.bar_chart(chart_df, color="#0d9488", height=300)
            with cc2:
                _chart_label(
                    "🚌 Số xe + Tốc độ mỗi tuyến",
                    "Cột Xe = cardinality(vehicle) — số xe duy nhất. "
                    "TB/Tối đa = avg/max(speed) lồng trong nhóm terms. "
                    "Tất cả chỉ số tính trên cùng tập bản ghi đã lọc.",
                )
                display_df = df_top[["route_no", "vehicles",
                                     "avg_speed", "max_speed"]].rename(columns={
                    "route_no":  "Tuyến",
                    "vehicles":  "Xe",
                    "avg_speed": "TB",
                    "max_speed": "Tối đa",
                })
                st.dataframe(display_df, hide_index=True,
                             use_container_width=True, height=300)
        else:
            st.info("Không có dữ liệu tuyến đứng đầu.")

        # ── Hàng 2: pings_per_min — số xe phân theo trạng thái di chuyển ──
        pm = api_get("/api/stats", {**base_params, "metric": "pings_per_min",
                                    "interval": "1m"})
        _chart_label(
            "📈 Số xe duy nhất theo phút — phân theo trạng thái",
            "Tổng hợp: date_histogram interval=1m → terms(vehicle) → "
            "max(speed). Mỗi xe được phân đúng 1 nhóm theo MAX(speed) trong "
            "phút (không trùng lặp): "
            "'Đang di chuyển' = max ≥ 5 km/h; "
            "'Dừng/đỗ' = max < 5 km/h hoặc speed=null (đèn đỏ, dừng trạm, "
            "đỗ tại bến phát tín hiệu). Tổng 2 nhóm = số xe duy nhất.",
            took_ms=pm.get("took", 0) if pm else 0,
        )
        if pm and pm.get("data"):
            df_pm = pd.DataFrame(pm["data"])
            df_pm["ts"] = pd.to_datetime(df_pm["ts"])

            chart_df = df_pm.set_index("ts")[
                ["active_vehicles", "moving", "stopped"]
            ].rename(columns={
                "active_vehicles": "Tổng xe trực tuyến",
                "moving":          "Đang di chuyển (≥5 km/h)",
                "stopped":         "Dừng/đỗ (<5 km/h)",
            })
            st.line_chart(chart_df, height=300,
                          color=["#475569", "#0d9488", "#f59e0b"])

            last = df_pm.iloc[-1]
            moving_pct = (last["moving"] / last["active_vehicles"] * 100
                          if last["active_vehicles"] else 0)
            st.caption(
                f"⚙ thời gian = {pm.get('took', 0)} ms · bước 1 phút · "
                f"phút mới nhất: {int(last['active_vehicles'])} xe trực tuyến "
                f"({int(last['moving'])} đang chạy — {moving_pct:.1f}%, "
                f"{int(last['stopped'])} dừng/đỗ)"
            )
        else:
            st.info("Không có dữ liệu.")

        # ── Hàng 3: speed_by_hour (24h cố định) + top jam routes ──────────
        cc5, cc6 = st.columns(2)
        with cc5:
            sh_params = {**base_params, "metric": "speed_by_hour",
                         "from": "now-24h", "to": "now"}
            sh = api_get("/api/stats", sh_params)
            _chart_label(
                "🕐 Tốc độ trung bình theo giờ trong 24h gần nhất",
                "Tổng hợp: date_histogram calendar_interval=1h + "
                "avg(speed, missing=0). Cửa sổ 24h cố định (không theo "
                "hàng lọc). missing=0 nghĩa là bản tin không có trường speed "
                "(xe đỗ tại bến, gói GPS tối giản) được tính "
                "như speed=0. Vì vậy trung bình toàn đoàn phản ánh đầy đủ: giờ vận "
                "hành ~20 km/h, giờ xe đỗ tụt gần 0.",
                took_ms=sh.get("took", 0) if sh else 0,
            )
            if sh and sh.get("data"):
                df_sh = pd.DataFrame(sh["data"])
                df_sh["ts"] = pd.to_datetime(df_sh["ts"])
                chart_df = df_sh.set_index("ts")[["avg_speed"]].rename(
                    columns={"avg_speed": "TB km/h"})
                st.line_chart(chart_df, height=260, color="#0d9488")
                st.caption(f"⚙ thời gian = {sh.get('took', 0)} ms · bước 1 giờ "
                           f"· missing=0 (xe đỗ tính như đứng yên)")
            else:
                st.info("Không có dữ liệu.")

        with cc6:
            tjr = api_get("/api/stats", {**base_params, "metric": "top_jam_routes",
                                         "size": 5})
            _chart_label(
                "🚧 Top tuyến kẹt nhất (% bản ghi speed < 5 km/h)",
                "Tổng hợp dạng pipeline: terms(route_no) size=50 + lọc "
                "speed<5 + bucket_script tính jam_pct = kẹt/tổng + "
                "bucket_sort sắp xếp jam_pct giảm dần. Lấy 50 tuyến đông xe "
                "trước rồi mới sắp xếp theo jam_pct (tránh tuyến nhỏ <100 "
                "bản tin bị nhiễu).",
                took_ms=tjr.get("took", 0) if tjr else 0,
            )
            if tjr and tjr.get("data"):
                df_jam = pd.DataFrame(tjr["data"])
                df_show = df_jam[["route_no", "route_name", "vehicles",
                                  "jam_pct", "avg_speed"]].rename(columns={
                    "route_no":   "Tuyến",
                    "route_name": "Tên tuyến",
                    "vehicles":   "Xe",
                    "jam_pct":    "% Kẹt",
                    "avg_speed":  "TB km/h",
                })
                st.dataframe(df_show, hide_index=True,
                             use_container_width=True, height=240)
            else:
                st.info("Không có dữ liệu.")

    render_stats()
