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
/* ── Global light gray theme ── */
[data-testid="stAppViewContainer"] {
    background: #ebeef2;
}
[data-testid="stMain"] {
    background: #ebeef2;
}

/* ── Route card buttons — left-align text ── */
button[data-testid="stBaseButton-secondary"],
button[data-testid="stBaseButton-primary"],
.stButton > button,
div[data-testid="stButton"] > button {
    justify-content: flex-start !important;
    text-align: left !important;
    padding-left: 16px !important;
}
button[data-testid="stBaseButton-secondary"] > div,
button[data-testid="stBaseButton-primary"] > div,
.stButton > button > div,
div[data-testid="stButton"] > button > div {
    text-align: left !important;
    width: 100% !important;
    justify-content: flex-start !important;
}
button[data-testid="stBaseButton-secondary"] p,
button[data-testid="stBaseButton-primary"] p,
.stButton > button p,
div[data-testid="stButton"] > button p {
    text-align: left !important;
    white-space: pre-wrap !important;
}

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #d0d7de;
    border-radius: 12px;
    padding: 20px 24px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0,179,164,0.15);
}
[data-testid="stMetricLabel"] {
    color: #57606a !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}
[data-testid="stMetricValue"] {
    color: #00b3a4 !important;
    font-size: 2.4rem !important;
    font-weight: 700 !important;
}

/* ── Section headers ── */
.section-header {
    color: #1f2328;
    font-size: 1.15rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    margin: 0.5rem 0 1rem 0;
    padding-bottom: 8px;
    border-bottom: 2px solid #d0d7de;
}

/* ── Search box accent ── */
[data-testid="stTextInput"] input {
    background: #ffffff !important;
    border-color: #d0d7de !important;
    color: #1f2328 !important;
    border-radius: 8px !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: #00b3a4 !important;
    box-shadow: 0 0 0 2px rgba(0,179,164,0.2) !important;
}

/* ── st_keyup: clip container thay vì iframe (JS override setFrameHeight(73)) ── */
[data-testid="stCustomComponentV1"] {
    height: 44px !important;
    min-height: unset !important;
    overflow: hidden !important;
}

/* ── Route result cards ── */
.route-badge {
    background: #0969da;
    color: #ffffff;
    border-radius: 8px;
    padding: 6px 4px;
    font-size: 0.95rem;
    font-weight: 700;
    text-align: center;
    line-height: 1.2;
    word-break: break-all;
}
.route-name {
    color: #1f2328;
    font-size: 1rem;
    font-weight: 600;
    margin: 0;
    line-height: 1.4;
}
.matched-stop {
    color: #1a7f37;
    font-size: 0.82rem;
    margin-top: 2px;
}
.selected-banner {
    background: rgba(0,179,164,0.08);
    border: 1px solid rgba(0,179,164,0.4);
    border-radius: 8px;
    padding: 8px 14px;
    color: #1f2328;
    font-size: 0.9rem;
}
.result-count {
    color: #57606a;
    font-size: 0.82rem;
    margin-bottom: 6px;
}

/* ── DataFrame ── */
[data-testid="stDataFrame"] {
    border: 1px solid #d0d7de;
    border-radius: 8px;
    overflow: hidden;
}

/* ── Divider ── */
hr { border-color: #d0d7de !important; }

/* ── Hide sidebar ── */
[data-testid="stSidebar"] { display: none; }
[data-testid="collapsedControl"] { display: none; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ────────────────────────────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(245,247,250,0.8)",
    font=dict(color="#1f2328", family="Inter, system-ui, sans-serif"),
    margin=dict(l=10, r=10, t=30, b=10),
    xaxis=dict(gridcolor="#d0d7de", zerolinecolor="#d0d7de"),
    yaxis=dict(gridcolor="#d0d7de", zerolinecolor="#d0d7de"),
)


def api_get(path: str, params: Optional[Dict] = None) -> Optional[Any]:
    """Call the FastAPI backend; return parsed JSON or None on error."""
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=8)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return None
    except Exception:
        return None


def speed_color(speed: float) -> List[int]:
    """Map speed 0–50+ km/h → RGB (green→yellow→red). Calibrated for HCMC traffic."""
    pct = min(speed / 50.0, 1.0)
    if pct < 0.5:
        return [int(255 * 2 * pct), 200, 0, 220]
    else:
        return [255, int(200 * (1 - 2 * (pct - 0.5))), 0, 220]


auto_refresh = True

# ── Common query params ────────────────────────────────────────────────────────
params_base = {"from": "now-1h", "to": "now+3h"}

if "selected_route_no" not in st.session_state:
    st.session_state["selected_route_no"] = ""
if "selected_route_name" not in st.session_state:
    st.session_state["selected_route_name"] = ""
if "selected_plate_no" not in st.session_state:
    st.session_state["selected_plate_no"] = ""

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='color:#1f2328; font-size:2rem; font-weight:800; margin-bottom:0'>🚌 Smart Bus GPS — Real-time Dashboard</h1>",
    unsafe_allow_html=True,
)


# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — Search Row (route search + plate filter side by side)
# ══════════════════════════════════════════════════════════════════════════════
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
    plate_data = api_get("/api/platesearch", {"route_no": st.session_state["selected_route_no"]})
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

# ── Selected route banner ───────────────────────────────────────────────────
selected_no   = st.session_state["selected_route_no"]
selected_name = st.session_state["selected_route_name"]
if selected_no:
    col_banner, col_clear = st.columns([7, 1])
    with col_banner:
        st.markdown(
            f"<div class='selected-banner'>🗺 Đang lọc: <b>Tuyến {selected_no}</b>"
            + (f" — {selected_name}" if selected_name else "")
            + "</div>",
            unsafe_allow_html=True,
        )
    with col_clear:
        if st.button("✕ Bỏ lọc", use_container_width=True):
            st.session_state["selected_route_no"] = ""
            st.session_state["selected_route_name"] = ""
            st.session_state["selected_plate_no"] = ""
            st.rerun()

# ── Search results as cards (ẩn khi đã chọn tuyến) ────────────────────────
if search_term.strip() and not st.session_state["selected_route_no"]:
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
            is_active  = route_no == st.session_state["selected_route_no"]

            color = "green" if is_active else "blue"
            card_label = f":{color}[**{route_no}**]   {route_name}" + (f"\n\n:gray[📍 *{stop}*]" if stop else "")
            if st.button(card_label, key=f"sel_{route_no}", use_container_width=True):
                st.session_state["selected_route_no"] = route_no
                st.session_state["selected_route_name"] = route_name
                st.session_state["selected_plate_no"] = ""
                st.rerun()
    elif search_data is not None:
        st.info(f"Không tìm thấy tuyến nào phù hợp với: **{search_term}**")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# Section 3 — Live Map + Route Info Panel
# ══════════════════════════════════════════════════════════════════════════════


def _stop_timeline_html(stops: list) -> str:
    if not stops:
        return "<p style='color:#57606a;font-size:0.82rem'>Không có dữ liệu.</p>"
    rows = []
    n = len(stops)
    for i, s in enumerate(stops):
        if i == 0:
            dot_bg, dot_border = "#00b3a4", "#00b3a4"
        elif i == n - 1:
            dot_bg, dot_border = "#eaecf0", "#57606a"
        else:
            dot_bg, dot_border = "#eaecf0", "#d0d7de"
        rows.append(
            f"<div style='display:flex;align-items:center;gap:10px;padding:5px 0'>"
            f"<span style='flex-shrink:0;width:12px;height:12px;border-radius:50%;"
            f"background:{dot_bg};border:2px solid {dot_border}'></span>"
            f"<span style='color:#1f2328;font-size:0.85rem'>{s}</span></div>"
        )
    return (
        "<div style='position:relative;padding-left:8px;margin:4px 0'>"
        "<div style='position:absolute;left:13px;top:0;bottom:0;width:2px;background:#d0d7de'></div>"
        + "".join(rows)
        + "</div>"
    )


def render_route_card(route: dict) -> None:
    rno  = route.get("route_no", "")
    name = route.get("route_name", "")
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px'>"
        f"<span style='background:#1f6feb;color:#fff;border-radius:6px;padding:4px 10px;"
        f"font-weight:700;font-size:0.95rem'>{rno}</span>"
        f"<span style='color:#1f2328;font-weight:600'>{name}</span></div>",
        unsafe_allow_html=True,
    )
    tab_info, tab_forward, tab_return = st.tabs(["ℹ️ Thông tin", "➡️ Lượt đi", "⬅️ Lượt về"])

    with tab_info:
        info_rows = [
            ("🕐 Giờ chạy",   route.get("schedule", "—")),
            ("⏱ Tần suất",    route.get("frequency", "—")),
            ("📏 Chiều dài",   route.get("length", "—")),
            ("💰 Giá vé",      route.get("fare", "—")),
            ("🔄 Chuyến/ngày", route.get("trips_per_day", "—")),
            ("🏢 Đơn vị",      route.get("operator", "—")),
        ]
        for label, val in info_rows:
            st.markdown(
                f"<div style='display:flex;gap:8px;padding:4px 0;border-bottom:1px solid #eaecf0'>"
                f"<span style='color:#57606a;min-width:110px;font-size:0.82rem'>{label}</span>"
                f"<span style='color:#1f2328;font-size:0.82rem'>{val}</span></div>",
                unsafe_allow_html=True,
            )

    with tab_forward:
        st.markdown(_stop_timeline_html(route.get("stops_forward", [])), unsafe_allow_html=True)

    with tab_return:
        st.markdown(_stop_timeline_html(route.get("stops_return", [])), unsafe_allow_html=True)


col_map, col_info = st.columns([3, 2])

with col_map:
    @st.fragment(run_every=f"{REFRESH_INTERVAL}s" if auto_refresh else None)
    def render_live_map():
        st.markdown('<div class="section-header">📍 Vị trí xe buýt (Live)</div>', unsafe_allow_html=True)

        now_str = pd.Timestamp.now().strftime("%H:%M:%S")
        st.markdown(f"<small style='color:#57606a; float:right; margin-top:-35px;'>🕐 Cập nhật: <b style='color:#00b3a4'>{now_str}</b></small>", unsafe_allow_html=True)

        params_pos = {**params_base, "max_vehicles": 500}
        route_filter = st.session_state.get("selected_route_no", "")
        route_name   = st.session_state.get("selected_route_name", "")
        plate_filter = st.session_state.get("selected_plate_no", "")
        if route_filter:
            params_pos["route_no"] = route_filter
            st.markdown(
                f"<small style='color:#00b3a4'>🗺 Tuyến <b>{route_filter}</b>"
                + (f": {route_name}" if route_name else "")
                + "</small>",
                unsafe_allow_html=True,
            )
        if plate_filter:
            params_pos["plate_no"] = plate_filter
            st.markdown(
                f"<small style='color:#00b3a4'>🚘 Biển số: <b>{plate_filter}</b></small>",
                unsafe_allow_html=True,
            )

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
                    "plate_no": p.get("plate_no", "") or p.get("vehicle", ""),
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
                    <div style='font-family:Inter,sans-serif; padding:8px; background:#ffffff; border-radius:8px;
                                border:1px solid #d0d7de; color:#1f2328; font-size:13px;'>
                        <b style='color:#00b3a4'>🚌 {plate_no}</b><br>
                        🗺 Tuyến {route_no}: {route_name}<br>
                        🚀 Tốc độ: <b>{speed} km/h</b><br>
                        🕐 {timestamp}
                    </div>
                """,
                "style": {"backgroundColor": "transparent", "border": "none"},
            }

            st.pydeck_chart(
                pdk.Deck(layers=[scatter_layer], initial_view_state=view_state, tooltip=tooltip, map_style=None),
                height=420,
            )
            st.caption(f"📍 {len(df_pos)} xe đang hiển thị | Màu: 🟢 chậm → 🔴 nhanh")
        else:
            st.info("Không có dữ liệu vị trí xe.")

    render_live_map()

with col_info:
    st.markdown('<div class="section-header">🗺 Thông tin Tuyến xe</div>', unsafe_allow_html=True)
    route_no_filter = st.session_state.get("selected_route_no", "")
    detail_data = api_get("/api/routedetail", {"route_no": route_no_filter} if route_no_filter else {})
    routes = detail_data.get("data", []) if detail_data else []

    with st.container(height=430, border=False):
        if not routes:
            st.info("Không có dữ liệu tuyến.")
        elif route_no_filter:
            render_route_card(routes[0])
        else:
            for route in routes:
                with st.expander(f"Tuyến {route.get('route_no','')} — {route.get('route_name','')}"):
                    render_route_card(route)

st.markdown("---")

st.markdown(
    "<div style='text-align:center; color:#57606a; font-size:0.78rem; padding:8px 0'>"
    "Smart Bus GPS Dashboard · Powered by FastAPI + Elasticsearch + Streamlit"
    "</div>",
    unsafe_allow_html=True,
)
