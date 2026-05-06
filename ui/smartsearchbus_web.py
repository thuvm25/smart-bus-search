"""
Smart Bus GPS — Streamlit Dashboard
Real-time visualization of bus GPS data via the FastAPI backend.

Run:
    streamlit run ui/smartsearchbus_web.py

Requires the FastAPI backend to be running:
    uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
"""

import os
from typing import Any, Dict, List, Optional

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st
from st_keyup import st_keyup

# ── Config ─────────────────────────────────────────────────────────────────────
API_BASE = os.getenv("API_BASE", "http://localhost:8000")
REFRESH_INTERVAL = 5  # seconds

# ── Page Setup ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🚌 Smart Bus GPS Dashboard",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"], [data-testid="stMain"] { background: #ebeef2; }

button[data-testid="stBaseButton-secondary"],
button[data-testid="stBaseButton-primary"],
.stButton > button,
div[data-testid="stButton"] > button {
    justify-content: flex-start !important;
    text-align: left !important;
    padding-left: 16px !important;
}
button[data-testid="stBaseButton-secondary"] > div,
.stButton > button > div { text-align: left !important; width: 100% !important; }
.stButton > button p { text-align: left !important; white-space: pre-wrap !important; }

[data-testid="stMetric"] {
    background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    border: 1px solid #d6d6d2;
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 4px 16px rgba(15,23,42,0.06);
}
[data-testid="stMetricLabel"] {
    color: #64748b !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
[data-testid="stMetricValue"] {
    color: #0d9488 !important;
    font-size: 1.9rem !important;
    font-weight: 700 !important;
}

.section-header {
    color: #0f172a;
    font-size: 1.1rem;
    font-weight: 700;
    margin: 0.5rem 0 0.8rem 0;
    padding-bottom: 6px;
    border-bottom: 2px solid #d6d6d2;
}

[data-testid="stTextInput"] input {
    background: #ffffff !important;
    border-color: #d6d6d2 !important;
    color: #0f172a !important;
    border-radius: 8px !important;
}
[data-testid="stCustomComponentV1"] {
    height: 44px !important;
    min-height: unset !important;
    overflow: hidden !important;
}

.selected-banner {
    background: rgba(13,148,136,0.10);
    border: 1px solid rgba(13,148,136,0.4);
    border-radius: 8px;
    padding: 8px 14px;
    color: #0f172a;
    font-size: 0.9rem;
}
.result-count { color: #57606a; font-size: 0.82rem; margin-bottom: 6px; }

.route-info-card {
    background: #ffffff;
    border: 1px solid #d6d6d2;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 8px;
}
.route-info-card .row {
    display: flex; gap: 8px; padding: 4px 0;
    font-size: 0.85rem; color: #334155;
}
.route-info-card .row b { color: #0f172a; min-width: 110px; }

[data-testid="stDataFrame"] {
    border: 1px solid #d6d6d2;
    border-radius: 8px;
    overflow: hidden;
}
hr { border-color: #d6d6d2 !important; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def api_get(path: str, params: Optional[Dict] = None) -> Optional[Any]:
    """Gọi FastAPI backend; trả None nếu lỗi."""
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=8)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return None
    except Exception:
        return None


def speed_color(speed: float) -> List[int]:
    """Map speed 0–50+ km/h → RGB (xanh→vàng→đỏ)."""
    pct = min(speed / 50.0, 1.0)
    if pct < 0.5:
        return [int(255 * 2 * pct), 200, 0, 220]
    return [255, int(200 * (1 - 2 * (pct - 0.5))), 0, 220]


def render_route_card(route: Dict) -> None:
    """Render route detail dạng card đơn giản."""
    rows = [
        ("Mã tuyến",      route.get("route_no", "")),
        ("Tên tuyến",     route.get("route_name", "")),
        ("Mô tả",         route.get("description", "")),
        ("Loại tuyến",    route.get("route_type", "")),
        ("Giá vé",        route.get("fare", "")),
        ("Độ dài",        route.get("length", "")),
        ("Thời gian chạy",route.get("schedule", "")),
        ("Giãn cách",     route.get("frequency", "")),
        ("Đơn vị",        route.get("operator", "")),
    ]
    html = "<div class='route-info-card'>"
    for label, val in rows:
        if val:
            html += f"<div class='row'><b>{label}:</b> {val}</div>"
    fwd = route.get("stops_forward") or []
    rtn = route.get("stops_return") or []
    if fwd:
        html += f"<div class='row'><b>Lượt đi ({len(fwd)} trạm):</b> {' → '.join(fwd[:6])}{' …' if len(fwd) > 6 else ''}</div>"
    if rtn:
        html += f"<div class='row'><b>Lượt về ({len(rtn)} trạm):</b> {' → '.join(rtn[:6])}{' …' if len(rtn) > 6 else ''}</div>"
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


# ── Session state ──────────────────────────────────────────────────────────────
for key in ("selected_route_no", "selected_route_name", "selected_plate_no"):
    if key not in st.session_state:
        st.session_state[key] = ""

params_base = {"from": "now-1h", "to": "now+3h"}
auto_refresh = True

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='color:#0f172a; font-size:2rem; font-weight:800; margin-bottom:0'>"
    "🚌 Smart Bus GPS — Real-time Dashboard</h1>",
    unsafe_allow_html=True,
)

# ══════════════════════════════════════════════════════════════════════════════
# TABS — tách rõ 4 chức năng để demo từng mục báo cáo
# ══════════════════════════════════════════════════════════════════════════════
tab_live, tab_stats, tab_filter, tab_routes = st.tabs([
    "📍 Live Map",
    "📊 Stats (Aggregation)",
    "🔎 Filter Explorer",
    "🗺 Route Detail",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — LIVE MAP + ROUTE / PLATE FILTER
# ══════════════════════════════════════════════════════════════════════════════
with tab_live:
    col_route, col_plate = st.columns([3, 2])

    with col_route:
        st.markdown('<div class="section-header">🔍 Tìm kiếm Tuyến xe</div>', unsafe_allow_html=True)
        search_term = st_keyup(
            "search",
            placeholder="VD: Chợ Rẫy, tuyến 05, Bến Thành...",
            label_visibility="collapsed",
            debounce=300,
        )

    with col_plate:
        st.markdown('<div class="section-header">🚘 Lọc theo Biển số xe</div>', unsafe_allow_html=True)
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
        default_idx = plate_options.index(current_plate) if current_plate in plate_options else 0

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

    # Selected route banner
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

    # Search results as cards
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
                color = "green" if route_no == st.session_state["selected_route_no"] else "blue"
                card_label = (
                    f":{color}[**{route_no}**]   {route_name}"
                    + (f"\n\n:gray[📍 *{stop}*]" if stop else "")
                )
                if st.button(card_label, key=f"sel_{route_no}", use_container_width=True):
                    st.session_state["selected_route_no"] = route_no
                    st.session_state["selected_route_name"] = route_name
                    st.session_state["selected_plate_no"] = ""
                    st.rerun()
        elif search_data is not None:
            st.info(f"Không tìm thấy tuyến nào phù hợp với: **{search_term}**")

    st.markdown("---")

    # Live map
    @st.fragment(run_every=f"{REFRESH_INTERVAL}s" if auto_refresh else None)
    def render_live_map():
        st.markdown('<div class="section-header">📍 Vị trí xe buýt (Live)</div>',
                    unsafe_allow_html=True)
        now_str = pd.Timestamp.now().strftime("%H:%M:%S")
        st.markdown(
            f"<small style='color:#64748b; float:right; margin-top:-35px;'>"
            f"🕐 Cập nhật: <b style='color:#0d9488'>{now_str}</b></small>",
            unsafe_allow_html=True,
        )

        params_pos = {**params_base, "max_vehicles": 500}
        if st.session_state.get("selected_route_no"):
            params_pos["route_no"] = st.session_state["selected_route_no"]
        if st.session_state.get("selected_plate_no"):
            params_pos["plate_no"] = st.session_state["selected_plate_no"]

        pos_data = api_get("/api/livebus", params_pos)
        if not pos_data or not pos_data.get("features"):
            st.info("Không có dữ liệu vị trí xe.")
            return

        points = []
        for f in pos_data["features"]:
            p = f["properties"]
            points.append({
                "lat":        p["lat"],
                "lon":        p["lon"],
                "speed":      p.get("speed", 0) or 0,
                "vehicle":    p.get("vehicle", ""),
                "route_no":   p.get("route_no", ""),
                "route_name": p.get("route_name", ""),
                "plate_no":   p.get("plate_no", ""),
                "timestamp":  p.get("timestamp", ""),
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
                <div style='font-family:Inter,sans-serif; padding:8px; background:#ffffff;
                            border-radius:8px; border:1px solid #d6d6d2; color:#0f172a;
                            font-size:13px; box-shadow:0 4px 16px rgba(15,23,42,0.12);'>
                    <b style='color:#0d9488'>🚌 {plate_no}</b><br>
                    🗺 Tuyến {route_no}: {route_name}<br>
                    🚀 Tốc độ: <b>{speed} km/h</b><br>
                    🕐 {timestamp}
                </div>
            """,
            "style": {"backgroundColor": "transparent", "border": "none"},
        }

        st.pydeck_chart(
            pdk.Deck(layers=[scatter_layer], initial_view_state=view_state,
                     tooltip=tooltip, map_style=None),
            height=500,
        )
        st.caption(f"📍 {len(df_pos)} xe đang hiển thị | Màu: 🟢 chậm → 🔴 nhanh")

    render_live_map()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — STATS (Aggregation) → /api/stats
# ══════════════════════════════════════════════════════════════════════════════
with tab_stats:
    st.markdown('<div class="section-header">📊 Aggregation </div>',
                unsafe_allow_html=True)

    col_a, col_b = st.columns([1, 1])
    with col_a:
        stats_window = st.selectbox(
            "Cửa sổ thời gian",
            options=["now-15m", "now-30m", "now-1h", "now-3h", "now-24h"],
            index=2,
        )
    with col_b:
        top_size = st.slider("Top N tuyến", min_value=3, max_value=20, value=5, step=1)

    # KPI row — vehicles_active metric
    kpi_data = api_get("/api/stats", {"metric": "vehicles_active",
                                      "from": stats_window, "to": "now"})
    if kpi_data and kpi_data.get("data"):
        d = kpi_data["data"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Xe đang hoạt động", f"{d['vehicles_active']:,}")
        c2.metric("Tuyến đang chạy",   f"{d['routes_in_use']:,}")
        c3.metric("Tổng ping",         f"{d['total_pings']:,}")
        c4.metric("Took (cold)",       f"{kpi_data.get('took', 0)} ms")
    else:
        st.warning("Backend chưa trả dữ liệu thống kê.")

    st.markdown("---")

    # Top routes bar chart
    top_data = api_get("/api/stats", {"metric": "top_routes",
                                      "from": stats_window, "to": "now",
                                      "size": top_size})
    if top_data and top_data.get("data"):
        df_top = pd.DataFrame(top_data["data"])

        col_chart, col_table = st.columns([3, 2])
        with col_chart:
            st.markdown(
                f"<div class='section-header'>Top {top_size} tuyến theo số ping "
                f"<span style='color:#64748b; font-weight:400; font-size:0.8em'>"
                f"(took {top_data.get('took', 0)} ms)</span></div>",
                unsafe_allow_html=True,
            )
            # Bar chart of pings per route
            chart_df = df_top.set_index("route_no")[["pings"]]
            st.bar_chart(chart_df, color="#0d9488", height=320)
        with col_table:
            st.markdown('<div class="section-header">Tốc độ (km/h)</div>',
                        unsafe_allow_html=True)
            display_df = df_top[["route_no", "route_name", "pings",
                                 "avg_speed", "max_speed"]].rename(columns={
                "route_no":   "Tuyến",
                "route_name": "Tên tuyến",
                "pings":      "Ping",
                "avg_speed":  "Avg",
                "max_speed":  "Max",
            })
            st.dataframe(display_df, hide_index=True, use_container_width=True,
                         height=320)
    else:
        st.info("Không có dữ liệu top routes.")

    st.markdown("---")

    # Speed distribution histogram
    col_speed, col_pings = st.columns(2)

    with col_speed:
        st.markdown('<div class="section-header">Phân bố tốc độ (histogram bin 5 km/h)</div>',
                    unsafe_allow_html=True)
        sd = api_get("/api/stats", {"metric": "speed_dist",
                                    "from": stats_window, "to": "now"})
        if sd and sd.get("data"):
            df_sd = pd.DataFrame(sd["data"])
            df_sd["bin"] = df_sd["speed_bin"].astype(int).astype(str) + "–" + \
                           (df_sd["speed_bin"].astype(int) + 5).astype(str)
            st.bar_chart(df_sd.set_index("bin")[["count"]],
                         color="#f59e0b", height=280)
            st.caption(f"⚙ took = {sd.get('took', 0)} ms")
        else:
            st.info("Không có dữ liệu.")

    with col_pings:
        st.markdown('<div class="section-header">Ping/phút trong cửa sổ</div>',
                    unsafe_allow_html=True)
        pm = api_get("/api/stats", {"metric": "pings_per_min",
                                    "from": stats_window, "to": "now",
                                    "interval": "1m"})
        if pm and pm.get("data"):
            df_pm = pd.DataFrame(pm["data"])
            df_pm["ts"] = pd.to_datetime(df_pm["ts"])
            df_pm = df_pm.set_index("ts")[["pings", "active_vehicles"]]
            st.line_chart(df_pm, height=280)
            st.caption(f"⚙ took = {pm.get('took', 0)} ms · interval 1m")
        else:
            st.info("Không có dữ liệu.")

    with st.expander("📡 ES query template — endpoint `/api/stats`"):
        st.code("""GET /bus_waypoints/_search
{
  "size": 0,
  "query": { "bool": { "filter": [
    { "range": { "@timestamp": { "gte": "now-1h" } } }
  ] } },
  "aggs": {
    "by_route": {
      "terms": { "field": "route_no", "size": 5, "order": { "_count": "desc" } },
      "aggs": {
        "avg_speed": { "avg": { "field": "speed" } },
        "max_speed": { "max": { "field": "speed" } },
        "min_speed": { "min": { "field": "speed" } }
      }
    }
  }
}""", language="json")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — FILTER EXPLORER → /api/filter
# ══════════════════════════════════════════════════════════════════════════════
with tab_filter:
    st.markdown('<div class="section-header">🔎 Filter Explorer </div>',
                unsafe_allow_html=True)

    with st.form("filter_form"):
        f1, f2, f3 = st.columns(3)
        with f1:
            fn_route = st.text_input("Mã tuyến (route_no)", value="",
                                     placeholder="VD: 50, 88, D4")
            fn_plate = st.text_input("Biển số (plate_no)", value="",
                                     placeholder="VD: 50F - 514.99")
        with f2:
            fn_ignition = st.selectbox("Trạng thái nổ máy",
                                       options=["", "true", "false"], index=0)
            fn_window = st.selectbox(
                "Cửa sổ thời gian",
                options=["now-15m", "now-30m", "now-1h", "now-3h", "now-24h"],
                index=2,
            )
        with f3:
            fn_speed_gte = st.number_input("Tốc độ ≥ (km/h)",
                                           min_value=0.0, max_value=200.0, value=0.0)
            fn_speed_lt  = st.number_input("Tốc độ < (km/h)",
                                           min_value=0.0, max_value=200.0, value=80.0)

        fn_size = st.slider("Số bản ghi mỗi trang", 10, 200, 50, step=10)
        submitted = st.form_submit_button("🔎 Lọc", use_container_width=False)

    if submitted or "filter_results" in st.session_state:
        params = {
            "from": fn_window if 'fn_window' in dir() else "now-1h",
            "to":   "now",
            "size": fn_size if 'fn_size' in dir() else 50,
        }
        if fn_route.strip():    params["route_no"] = fn_route.strip()
        if fn_plate.strip():    params["plate_no"] = fn_plate.strip()
        if fn_ignition:         params["ignition"] = fn_ignition
        if fn_speed_gte > 0:    params["speed_gte"] = fn_speed_gte
        if fn_speed_lt < 200:   params["speed_lt"]  = fn_speed_lt

        result = api_get("/api/filter", params)
        if result:
            st.session_state["filter_results"] = result

            top_a, top_b, top_c = st.columns(3)
            top_a.metric("Tổng hit",    f"{result.get('total', 0):,}")
            top_b.metric("Đang hiển thị", f"{len(result.get('data', [])):,}")
            top_c.metric("Took",        f"{result.get('took', 0)} ms")

            with st.expander("⚙️ Filter clause đã áp dụng"):
                st.json(result.get("applied_filters", {}))

            if result.get("data"):
                df = pd.DataFrame(result["data"])
                # Round speed cho gọn
                if "speed" in df.columns:
                    df["speed"] = df["speed"].round(1)

                # Map (chỉ visualize document trả về của filter — không phải geo query)
                df_geo = df.dropna(subset=["lat", "lon"]).copy()
                if not df_geo.empty:
                    df_geo["color"] = df_geo["speed"].fillna(0).apply(speed_color)

                    map_col, table_col = st.columns([1, 1])
                    with map_col:
                        st.markdown(
                            "<div class='section-header'>Vị trí bản ghi khớp filter</div>",
                            unsafe_allow_html=True,
                        )
                        scatter = pdk.Layer(
                            "ScatterplotLayer",
                            data=df_geo,
                            get_position=["lon", "lat"],
                            get_fill_color="color",
                            get_radius=70,
                            pickable=True,
                            auto_highlight=True,
                            radius_min_pixels=3,
                            radius_max_pixels=12,
                        )
                        view_state = pdk.ViewState(
                            latitude=float(df_geo["lat"].mean()),
                            longitude=float(df_geo["lon"].mean()),
                            zoom=11, pitch=0,
                        )
                        tooltip = {
                            "html": """
                                <div style='font-family:Inter,sans-serif; padding:8px;
                                            background:#ffffff; border-radius:8px;
                                            border:1px solid #d6d6d2; color:#0f172a;
                                            font-size:12px;
                                            box-shadow:0 4px 16px rgba(15,23,42,0.12);'>
                                    <b style='color:#0d9488'>🚌 {plate_no}</b><br>
                                    🗺 Tuyến {route_no}: {route_name}<br>
                                    🚀 {speed} km/h · 🕐 {timestamp}
                                </div>
                            """,
                            "style": {"backgroundColor": "transparent", "border": "none"},
                        }
                        st.pydeck_chart(
                            pdk.Deck(layers=[scatter], initial_view_state=view_state,
                                     tooltip=tooltip, map_style=None),
                            height=420,
                        )
                        st.caption(
                            f"📍 {len(df_geo)} điểm · màu theo tốc độ (🟢 chậm → 🔴 nhanh)"
                        )
                    with table_col:
                        st.markdown(
                            "<div class='section-header'>Bảng kết quả</div>",
                            unsafe_allow_html=True,
                        )
                        cols_priority = ["timestamp", "plate_no", "route_no", "speed",
                                         "ignition", "lat", "lon"]
                        df_show = df[[c for c in cols_priority if c in df.columns]]
                        st.dataframe(df_show, hide_index=True,
                                     use_container_width=True, height=420)
                else:
                    # Không có lat/lon hợp lệ → fallback chỉ hiển thị bảng
                    cols_priority = ["timestamp", "plate_no", "route_no", "route_name",
                                     "speed", "lat", "lon", "ignition", "aircon", "vehicle"]
                    df_show = df[[c for c in cols_priority if c in df.columns]]
                    st.dataframe(df_show, hide_index=True,
                                 use_container_width=True, height=420)
            else:
                st.info("Không có bản ghi nào khớp với bộ lọc.")
        else:
            st.error("Backend không phản hồi — kiểm tra `/api/filter` ở Swagger.")

    with st.expander("📡 ES query template — endpoint `/api/filter`"):
        st.code("""GET /bus_waypoints/_search
{
  "size": 50,
  "track_total_hits": true,
  "query": {
    "bool": { "filter": [
      { "range": { "@timestamp": { "gte": "now-1h", "lte": "now" } } },
      { "term":  { "route_no": "50" } },
      { "term":  { "ignition": true } },
      { "range": { "speed": { "gte": 0, "lt": 60 } } }
    ] }
  },
  "sort": [ { "@timestamp": { "order": "desc" } } ]
}""", language="json")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — ROUTE DETAIL → /api/routedetail
# ══════════════════════════════════════════════════════════════════════════════
with tab_routes:
    st.markdown('<div class="section-header">🗺 Thông tin Tuyến xe</div>',
                unsafe_allow_html=True)

    route_no_filter = st.session_state.get("selected_route_no", "")
    detail_data = api_get("/api/routedetail",
                          {"route_no": route_no_filter} if route_no_filter else {})
    routes = detail_data.get("data", []) if detail_data else []

    if not routes:
        st.info("Không có dữ liệu tuyến — chọn tuyến từ tab Live Map.")
    elif route_no_filter:
        render_route_card(routes[0])
    else:
        for route in routes:
            with st.expander(f"Tuyến {route.get('route_no','')} — {route.get('route_name','')}"):
                render_route_card(route)


st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#64748b; font-size:0.78rem; padding:8px 0'>"
    "Smart Bus GPS Dashboard · FastAPI + Elasticsearch + Streamlit · "
    "6 endpoint REST: livebus · fuzzysearch · platesearch · routedetail · stats · filter"
    "</div>",
    unsafe_allow_html=True,
)
