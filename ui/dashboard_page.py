"""
Smart Bus GPS — "Dashboard" page.

Fuzzy route search + live map of all buses, refreshed on a fragment timer.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import pydeck as pdk
import streamlit as st


ApiGet = Callable[[str, Optional[Dict]], Optional[Any]]
SpeedColor = Callable[[float], List[int]]

REFRESH_INTERVAL = 5  # seconds


def render_dashboard_page(api_get: ApiGet, speed_color: SpeedColor) -> None:
    st.markdown(
        "<h1 style='color:#e6edf3; font-size:2rem; font-weight:800; margin-bottom:0'>"
        "🚌 Smart Bus GPS — Real-time Dashboard</h1>",
        unsafe_allow_html=True,
    )

    auto_refresh = st.sidebar.checkbox("🔄 Auto-refresh (5s)", value=True)
    st.sidebar.markdown("---")

    params_base = {"from": "now-1h", "to": "now+3h"}
    st.session_state.setdefault("selected_route_no", "")

    st.markdown('<div class="section-header">🔍 Tìm kiếm Tuyến xe</div>', unsafe_allow_html=True)

    search_col, _ = st.columns([2, 3])
    search_term = search_col.text_input(
        "Nhập tên tuyến (fuzzy search):",
        placeholder="VD: Bến Thành, Suối Tiên...",
        label_visibility="collapsed",
    )

    search_data = api_get("/api/fuzzysearch", {**params_base, "size": 50, "q": search_term})
    if search_data and search_data.get("data"):
        df_search = pd.DataFrame(search_data["data"])
        df_search = df_search[df_search["route_name"] != "Unknown"]
        if not df_search.empty:
            route_options = [("", "📍 Tất cả tuyến")] + [
                (str(r["route_no"]), f"Tuyến {r['route_no']} — {r['route_name']}")
                for _, r in df_search.iterrows()
                if r["route_no"]
            ]
            labels = [o[1] for o in route_options]

            if search_term.strip():
                auto_no = route_options[1][0] if len(route_options) > 1 else ""
                if st.session_state["selected_route_no"] != auto_no:
                    st.session_state["selected_route_no"] = auto_no

            current = st.session_state["selected_route_no"]
            current_idx = next((i for i, o in enumerate(route_options) if o[0] == current), 0)
            chosen = st.selectbox("🗺 Chọn tuyến để xem trên bản đồ:", labels, index=current_idx)
            st.session_state["selected_route_no"] = route_options[labels.index(chosen)][0]
        else:
            st.session_state["selected_route_no"] = ""
            st.info(f"Không tìm thấy tuyến nào với từ khoá: **{search_term}**")
    elif search_term.strip() == "":
        st.session_state["selected_route_no"] = ""

    st.markdown("---")

    st.markdown('<div class="section-header">📍 Vị trí xe buýt (Live)</div>', unsafe_allow_html=True)
    col_map = st.container()

    @st.fragment(run_every=f"{REFRESH_INTERVAL}s" if auto_refresh else None)
    def render_live_map():
        now_str = pd.Timestamp.now().strftime("%H:%M:%S")
        st.markdown(
            f"<small style='color:#8b949e; float:right; margin-top:-35px;'>"
            f"🕐 Cập nhật: <b style='color:#00b3a4'>{now_str}</b></small>",
            unsafe_allow_html=True,
        )

        params_pos = {**params_base, "max_vehicles": 500}
        route_filter = st.session_state.get("selected_route_no", "")
        if route_filter:
            params_pos["route_no"] = route_filter

        pos_data = api_get("/api/livebus", params_pos)
        if pos_data and pos_data.get("features"):
            points = []
            for f in pos_data["features"]:
                p = f["properties"]
                points.append({
                    "lat": p["lat"],
                    "lon": p["lon"],
                    "speed": p.get("speed", 0) or 0,
                    "vehicle": p.get("vehicle", ""),
                    "route_no": p.get("route_no", ""),
                    "route_name": p.get("route_name", ""),
                    "timestamp": p.get("timestamp", ""),
                })
            df_pos = pd.DataFrame(points)
            df_pos["color"] = df_pos["speed"].apply(speed_color)

            scatter_layer = pdk.Layer(
                "ScatterplotLayer",
                data=df_pos,
                get_position=["lon", "lat"],
                get_fill_color="color",
                get_radius=80,
                pickable=True,
                auto_highlight=True,
                radius_min_pixels=4,
                radius_max_pixels=16,
            )

            view_state = pdk.ViewState(latitude=10.78, longitude=106.66, zoom=11, pitch=0)

            tooltip = {
                "html": """
                    <div style='font-family:Inter,sans-serif; padding:8px; background:#21262d; border-radius:8px;
                                border:1px solid #30363d; color:#e6edf3; font-size:13px;'>
                        <b style='color:#00b3a4'>🚌 {vehicle}</b><br>
                        🗺 Tuyến {route_no}: {route_name}<br>
                        🚀 Tốc độ: <b>{speed} km/h</b><br>
                        🕐 {timestamp}
                    </div>
                """,
                "style": {"backgroundColor": "transparent", "border": "none"}
            }

            st.pydeck_chart(
                pdk.Deck(
                    layers=[scatter_layer],
                    initial_view_state=view_state,
                    tooltip=tooltip,
                    map_style=None,
                ),
                height=420,
            )
            st.caption(f"📍 {len(df_pos)} xe đang hiển thị | Màu: 🟢 chậm → 🔴 nhanh")
        else:
            st.info("Không có dữ liệu vị trí xe.")

    with col_map:
        render_live_map()
