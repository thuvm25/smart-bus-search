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
    padding: 14px 18px;
    box-shadow: 0 4px 16px rgba(15,23,42,0.06);
}
[data-testid="stMetricLabel"] {
    color: #64748b !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
[data-testid="stMetricValue"] {
    color: #0d9488 !important;
    font-size: 1.6rem !important;
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

.filter-chip {
    display: inline-block;
    background: rgba(13,148,136,0.10);
    color: #0d9488;
    border-radius: 999px;
    padding: 2px 10px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-right: 6px;
}

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

[data-testid="stSidebar"] { display: none; }
[data-testid="collapsedControl"] { display: none; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def api_get(path: str, params: Optional[Dict] = None) -> Optional[Any]:
    """Call FastAPI; return None on error."""
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


def chart_label(title: str, help_text: str, took_ms: int = 0) -> None:
    """Render chart label dùng st.markdown(help=...) để có (?) icon
    + tooltip Streamlit native — giống hệt st.metric."""
    took_suffix = (f" <span style='color:#64748b; font-weight:400; "
                   f"font-size:0.85em; margin-left:8px'>"
                   f"took {took_ms} ms</span>") if took_ms else ""
    st.markdown(
        f"**{title}**{took_suffix}",
        unsafe_allow_html=True,
        help=help_text,
    )


def render_route_card(route: Dict) -> None:
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


# ── Session state ──────────────────────────────────────────────────────────────
DEFAULTS = {
    "selected_route_no":   "",
    "selected_route_name": "",
    "selected_plate_no":   "",
    # Bộ lọc nâng cao — feed thẳng vào bool.filter của /api/livebus + /api/stats
    "filter_window":       "now-1h",
    "filter_ignition":     "—",
    "filter_speed_min":    0,
    "filter_speed_max":    80,
}
for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val



# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='color:#0f172a; font-size:2rem; font-weight:800; margin-bottom:0'>"
    "🚌 Smart Bus GPS — Real-time Dashboard</h1>",
    unsafe_allow_html=True,
)


# ══════════════════════════════════════════════════════════════════════════════
# Hàng 1 — Search tuyến + lọc biển số
# ══════════════════════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════════════════════
# Hàng 2 — Bộ lọc nâng cao (luôn hiển thị, không wrap expander)
# ══════════════════════════════════════════════════════════════════════════════
fc1, fc2, fc3, fc4 = st.columns([1, 1, 2, 0.6])

with fc1:
    st.session_state["filter_window"] = st.selectbox(
        "Cửa sổ thời gian",
        options=["now-15m", "now-30m", "now-1h", "now-3h", "now-24h"],
        index=["now-15m", "now-30m", "now-1h", "now-3h", "now-24h"].index(
            st.session_state["filter_window"]),
        help="Áp clause `range` lên @timestamp",
    )

with fc2:
    st.session_state["filter_ignition"] = st.selectbox(
        "Trạng thái nổ máy",
        options=["—", "Đang nổ máy", "Đã tắt máy"],
        index=["—", "Đang nổ máy", "Đã tắt máy"].index(
            st.session_state["filter_ignition"]),
        help="Áp clause `term` lên field `ignition` (boolean)",
    )

with fc3:
    speed_min, speed_max = st.slider(
        "Khoảng tốc độ (km/h)",
        min_value=0, max_value=120,
        value=(st.session_state["filter_speed_min"],
               st.session_state["filter_speed_max"]),
        help="Áp clause `range` lên field `speed`",
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


# ══════════════════════════════════════════════════════════════════════════════
# Selected route banner + clear button
# ══════════════════════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════════════════════
# Search results as cards
# ══════════════════════════════════════════════════════════════════════════════
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

st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# Live map + route detail (2 cột)
# ══════════════════════════════════════════════════════════════════════════════
col_map, col_info = st.columns([3, 2])


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


with col_map:
    # Selectbox chọn chu kỳ auto-refresh (đặt ngoài fragment để re-định nghĩa
    # fragment với run_every mới mỗi khi đổi giá trị)
    head_col, sel_col = st.columns([7, 2])
    with head_col:
        st.markdown('<div class="section-header">📍 Vị trí xe buýt</div>',
                    unsafe_allow_html=True)
    with sel_col:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        interval_label = st.selectbox(
            "Tự refresh",
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
        suffix = (f" · auto {_refresh_sec}s" if _refresh_sec
                  else " · không auto-refresh")
        st.caption(f"🕐 Cập nhật lần cuối: **{last_refresh}**{suffix}")

        params_pos = _build_livebus_params()
        pos_data = api_get("/api/livebus", params_pos)

        if not pos_data or not pos_data.get("features"):
            st.info("Không có dữ liệu vị trí xe khớp bộ lọc.")
            return

        clauses = pos_data.get("filter_clauses_count", 0)
        took    = pos_data.get("took", 0)
        count   = pos_data.get("count", len(pos_data["features"]))

        k1, k2, k3 = st.columns(3)
        k1.metric("Xe khớp",        f"{count}")
        k2.metric("Filter clauses", f"{clauses}")
        k3.metric("Took",           f"{took} ms")

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
                "plate_no":   p.get("plate_no", "") or p.get("vehicle", ""),
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
        view_state = pdk.ViewState(latitude=10.78, longitude=106.66,
                                   zoom=11, pitch=0)
        tooltip = {
            "html": """
                <div style='font-family:Inter,sans-serif; padding:8px;
                            background:#ffffff; border-radius:8px;
                            border:1px solid #d6d6d2; color:#0f172a;
                            font-size:13px;
                            box-shadow:0 4px 16px rgba(15,23,42,0.12);'>
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
            height=460,
        )
        st.caption("Màu chấm: 🟢 chậm → 🔴 nhanh")

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
            render_route_card(routes[0])
        else:
            for route in routes[:20]:
                with st.expander(
                    f"Tuyến {route.get('route_no','')} — "
                    f"{route.get('route_name','')}"
                ):
                    render_route_card(route)


st.markdown("---")


# ══════════════════════════════════════════════════════════════════════════════
# Aggregation panel — /api/stats (manual refresh, không auto-refresh)
# ══════════════════════════════════════════════════════════════════════════════
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
    parts: list = [f"`{st.session_state['filter_window']}` → now"]
    if st.session_state.get("selected_route_no"):
        parts.append(f"route_no=`{st.session_state['selected_route_no']}`")
    if st.session_state.get("selected_plate_no"):
        parts.append(f"plate=`{st.session_state['selected_plate_no']}`")
    ign = st.session_state.get("filter_ignition", "—")
    if ign != "—":
        parts.append(f"ignition=`{ign}`")
    s_min = st.session_state.get("filter_speed_min", 0)
    s_max = st.session_state.get("filter_speed_max", 80)
    if s_min > 0 or s_max < 120:
        parts.append(f"speed=`{s_min}–{s_max}`")
    return " · ".join(parts)


@st.fragment
def render_stats():
    head_col, btn_col = st.columns([8, 1.2])
    with head_col:
        st.markdown('<div class="section-header">📊 Thống kê (Aggregation)</div>',
                    unsafe_allow_html=True)
    with btn_col:
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.button("🔄 Làm mới", key="refresh_stats",
                  use_container_width=True)

    base_params = _build_stats_params()
    last_refresh = pd.Timestamp.now().strftime("%H:%M:%S")
    st.caption(f"🕐 Cập nhật lần cuối: **{last_refresh}** · {_filter_summary()}")

    # ── Hàng KPI 1: tổng quan vận hành ─────────────────────────────────────
    kpi_data = api_get("/api/stats", {**base_params, "metric": "vehicles_active"})
    jam_data = api_get("/api/stats", {**base_params, "metric": "traffic_jam"})

    if kpi_data and kpi_data.get("data"):
        d = kpi_data["data"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Xe đang hoạt động",
            f"{d['vehicles_active']:,}",
            help="Số xe DUY NHẤT có ít nhất 1 bản ghi GPS trong cửa sổ. "
                 "Aggregation: cardinality(vehicle).",
        )
        c2.metric(
            "Tuyến đang chạy",
            f"{d['routes_in_use']:,}",
            help="Số tuyến DUY NHẤT có xe vận hành trong cửa sổ. "
                 "Aggregation: cardinality(route_no).",
        )
        if jam_data and jam_data.get("data"):
            c3.metric(
                "Tỷ lệ kẹt xe",
                f"{jam_data['data']['jam_pct']}%",
                help="% bản tin GPS có vận tốc < 5 km/h trong cửa sổ. "
                     "Đại diện cho mức độ ùn tắc + dừng đèn đỏ + dừng "
                     "trạm. Aggregation: range(speed) chia 4 nhóm "
                     "jam/slow/normal/fast rồi lấy tỷ lệ jam/total.",
            )
        else:
            c3.metric("Tỷ lệ kẹt xe", "—")
        c4.metric(
            "Took",
            f"{kpi_data.get('took', 0)} ms",
            help="Thời gian Elasticsearch xử lý query (took field). "
                 "Đo nội bộ ES, không bao gồm network round-trip.",
        )
    else:
        st.warning("Backend chưa trả dữ liệu thống kê.")

    # ── Top N tuyến ─────────────────────────────────────────────────────────
    top_size = st.slider(
        "Top N tuyến", 3, 20, 5, step=1, key="stats_top_size",
        help="Tham số `size` của terms aggregation. ES sẽ trả N tuyến có "
             "nhiều xe nhất. N nhỏ = dashboard gọn; N lớn = thấy "
             "phân bố rộng hơn.",
    )

    top_data = api_get("/api/stats", {**base_params, "metric": "top_routes",
                                      "size": top_size})
    if top_data and top_data.get("data"):
        df_top = pd.DataFrame(top_data["data"])

        cc1, cc2 = st.columns([3, 2])
        with cc1:
            chart_label(
                f"📊 Top {top_size} tuyến theo số xe đang vận hành",
                f"Aggregation: terms(route_no) size={top_size} order _count desc, "
                f"sub-agg cardinality(vehicle) lấy số xe duy nhất. "
                f"Tuyến đông xe = tuyến hoạt động sôi nổi nhất.",
                took_ms=top_data.get("took", 0),
            )
            chart_df = df_top.set_index("route_no")[["vehicles"]]
            st.bar_chart(chart_df, color="#0d9488", height=300)
        with cc2:
            chart_label(
                "🚌 Số xe + Tốc độ mỗi tuyến",
                "Cột Xe = cardinality(vehicle) — số xe duy nhất. "
                "Avg/Max = avg/max(speed) lồng trong terms bucket. "
                "Tất cả metric tính trên cùng tập document đã lọc.",
            )
            display_df = df_top[["route_no", "vehicles",
                                 "avg_speed", "max_speed"]].rename(columns={
                "route_no":  "Tuyến",
                "vehicles":  "Xe",
                "avg_speed": "Avg",
                "max_speed": "Max",
            })
            st.dataframe(display_df, hide_index=True,
                         use_container_width=True, height=300)
    else:
        st.info("Không có dữ liệu top routes.")

    # ── Hàng 2: pings_per_min — số xe phân theo trạng thái di chuyển ────────
    pm = api_get("/api/stats", {**base_params, "metric": "pings_per_min",
                                "interval": "1m"})
    chart_label(
        "📈 Số xe duy nhất theo phút — phân theo trạng thái",
        "Aggregation: date_histogram interval=1m + 2 filter sub-agg "
        "lồng cardinality(vehicle). 'Đang di chuyển' = xe có ping "
        "speed ≥ 5 km/h; 'Dừng đèn đỏ/trạm' = xe có ping 1 ≤ speed < 5 "
        "km/h (dataset gốc không có speed=0 — GPS clamp tối thiểu = 1.0 "
        "do noise). Xe đỗ depot (speed=null) không tính.",
        took_ms=pm.get("took", 0) if pm else 0,
    )
    if pm and pm.get("data"):
        df_pm = pd.DataFrame(pm["data"])
        df_pm["ts"] = pd.to_datetime(df_pm["ts"])
        df_pm = df_pm.set_index("ts")[["moving", "stopped"]].rename(columns={
            "moving":  "🟢 Đang di chuyển",
            "stopped": "🟠 Dừng đèn đỏ / dừng trạm",
        })
        st.line_chart(df_pm, height=260, color=["#0d9488", "#f59e0b"])
    else:
        st.info("Không có dữ liệu.")

    # ── Hàng 3: speed_by_hour (24h cố định) + top jam routes ───────────────
    cc5, cc6 = st.columns(2)
    with cc5:
        # Override cửa sổ thành 24h cố định cho widget này
        sh_params = {**base_params, "metric": "speed_by_hour",
                     "from": "now-24h", "to": "now"}
        sh = api_get("/api/stats", sh_params)
        chart_label(
            "🕐 Tốc độ trung bình theo giờ trong 24h gần nhất",
            "Aggregation: date_histogram calendar_interval=1h + "
            "avg(speed, missing=0). Cửa sổ 24h cố định (không theo "
            "filter row). missing=0 nghĩa là ping không có field speed "
            "(xe đỗ tại depot, GPS minimal payload mode) được tính "
            "như speed=0. Vì vậy fleet avg phản ánh đầy đủ: giờ vận "
            "hành ~20 km/h, giờ xe đỗ tụt gần 0.",
            took_ms=sh.get("took", 0) if sh else 0,
        )
        if sh and sh.get("data"):
            df_sh = pd.DataFrame(sh["data"])
            df_sh["ts"] = pd.to_datetime(df_sh["ts"])
            chart_df = df_sh.set_index("ts")[["avg_speed"]].rename(
                columns={"avg_speed": "Avg km/h"})
            st.line_chart(chart_df, height=260, color="#0d9488")
            st.caption(f"⚙ took = {sh.get('took', 0)} ms · interval 1h "
                       f"· missing=0 (xe đỗ tính như đứng yên)")
        else:
            st.info("Không có dữ liệu.")

    with cc6:
        tjr = api_get("/api/stats", {**base_params, "metric": "top_jam_routes",
                                     "size": 5})
        chart_label(
            "🚧 Top tuyến kẹt nhất (% bản ghi speed < 5 km/h)",
            "Aggregation pipeline: terms(route_no) size=50 + filter "
            "speed<5 + bucket_script tính jam_pct = jam/total + "
            "bucket_sort sort jam_pct desc. Lấy top 50 tuyến đông xe "
            "trước rồi mới sort theo jam_pct (tránh tuyến nhỏ <100 "
            "ping bị nhiễu).",
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
                "avg_speed":  "Avg km/h",
            })
            st.dataframe(df_show, hide_index=True,
                         use_container_width=True, height=240)
        else:
            st.info("Không có dữ liệu.")


render_stats()


st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#64748b; font-size:0.78rem; padding:8px 0'>"
    "Smart Bus GPS Dashboard · FastAPI + Elasticsearch + Streamlit · "
    "Endpoints: livebus · fuzzysearch · platesearch · routedetail · stats"
    "</div>",
    unsafe_allow_html=True,
)
