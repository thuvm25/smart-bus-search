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

# ── Config ─────────────────────────────────────────────────────────────────────
API_BASE = os.getenv("API_BASE", "http://localhost:8000")
REFRESH_INTERVAL = 5  # seconds

# ── Page Setup ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🚌 Smart Bus GPS Dashboard",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Global dark theme tweaks ── */
[data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #161b22 0%, #1c2128 100%);
    border-right: 1px solid #30363d;
}

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #1c2128 0%, #21262d 100%);
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 20px 24px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.4);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(0,179,164,0.2);
}
[data-testid="stMetricLabel"] {
    color: #8b949e !important;
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
[data-testid="stMetricDelta"] {
    font-size: 0.8rem !important;
}

/* ── Section headers ── */
.section-header {
    color: #e6edf3;
    font-size: 1.15rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    margin: 0.5rem 0 1rem 0;
    padding-bottom: 8px;
    border-bottom: 2px solid #30363d;
}

/* ── Status badge ── */
.status-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.04em;
}
.status-online { background: rgba(35,197,94,0.15); color: #23c55e; border: 1px solid #23c55e44; }

/* ── Search box accent ── */
[data-testid="stTextInput"] input {
    background: #21262d !important;
    border-color: #30363d !important;
    color: #e6edf3 !important;
    border-radius: 8px !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: #00b3a4 !important;
    box-shadow: 0 0 0 2px rgba(0,179,164,0.2) !important;
}

/* ── DataFrame ── */
[data-testid="stDataFrame"] {
    border: 1px solid #30363d;
    border-radius: 8px;
    overflow: hidden;
}

/* ── Divider ── */
hr { border-color: #30363d !important; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ────────────────────────────────────────────────────────────────────
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(28,33,40,0.8)",
    font=dict(color="#c9d1d9", family="Inter, system-ui, sans-serif"),
    margin=dict(l=10, r=10, t=30, b=10),
    xaxis=dict(gridcolor="#30363d", zerolinecolor="#30363d"),
    yaxis=dict(gridcolor="#30363d", zerolinecolor="#30363d"),
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


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🚌 Smart Bus GPS")
    st.markdown("---")
    auto_refresh = st.checkbox("🔄 Auto-refresh (5s)", value=True)
    st.markdown("---")
    st.info("Trang web chuyên dụng tìm kiếm và theo dõi xe buýt thời gian thực.")

# ── Common query params (Hardcoded for clean UI) ────────────────────────────────
params_base = {"from": "now-1h", "to": "now+3h"}

if "selected_route_no" not in st.session_state:
    st.session_state["selected_route_no"] = ""

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='color:#e6edf3; font-size:2rem; font-weight:800; margin-bottom:0'>🚌 Smart Bus GPS — Real-time Dashboard</h1>",
    unsafe_allow_html=True,
)


# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — Fuzzy Search
# ══════════════════════════════════════════════════════════════════════════════
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

        # Auto-select first match when user has typed a search term
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
    # Reset selection when search is cleared
    st.session_state["selected_route_no"] = ""

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# Section 2 — Live Map
# ══════════════════════════════════════════════════════════════════════════════
col_map = st.container()

@st.fragment(run_every=f"{REFRESH_INTERVAL}s" if auto_refresh else None)
def render_live_map():
    st.markdown('<div class="section-header">📍 Vị trí xe buýt (Live)</div>', unsafe_allow_html=True)
    
    now_str = pd.Timestamp.now().strftime("%H:%M:%S")
    st.markdown(f"<small style='color:#8b949e; float:right; margin-top:-35px;'>🕐 Cập nhật: <b style='color:#00b3a4'>{now_str}</b></small>", unsafe_allow_html=True)
    
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

        view_state = pdk.ViewState(
            latitude=10.78,
            longitude=106.66,
            zoom=11,
            pitch=0,
        )

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

st.markdown("---")

st.markdown(
    "<div style='text-align:center; color:#8b949e; font-size:0.78rem; padding:8px 0'>"
    "Smart Bus GPS Dashboard · Powered by FastAPI + Elasticsearch + Streamlit"
    "</div>",
    unsafe_allow_html=True,
)
