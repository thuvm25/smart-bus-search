"""
Smart Bus GPS — Streamlit Dashboard
Real-time visualization of bus GPS data via the FastAPI backend.

Run:
    streamlit run ui/smartsearchbus_web.py

Each sidebar tab is a real page with its own URL:
    /dashboard   — comprehensive live dashboard (search, plate filter,
                   advanced filters, live map, route detail, stats)
    /nearby      — buses & stops within radius
    /activity    — most active buses + per-bus track

Requires the FastAPI backend to be running:
    uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
"""

import os
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

from activity_page import render_activity_page
from dashboard_page import render_dashboard_page

# ── Config ─────────────────────────────────────────────────────────────────────
API_BASE = os.getenv("API_BASE", "http://localhost:8000")

# ── Page Setup ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Smart Bus GPS — Dashboard",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"], [data-testid="stMain"] { background: #ebeef2; }

div[data-testid="stButton"] button,
.stButton button,
button[kind="secondary"],
button[data-testid="baseButton-secondary"] {
    display: block !important;
    text-align: left !important;
    padding-left: 16px !important;
    padding-top: 10px !important;
    padding-bottom: 10px !important;
    width: 100% !important;
}
div[data-testid="stButton"] button > div,
.stButton button > div,
button[kind="secondary"] > div,
button[data-testid="baseButton-secondary"] > div,
div[data-testid="stButton"] button p,
.stButton button p,
button[kind="secondary"] p,
button[data-testid="baseButton-secondary"] p {
    display: block !important;
    text-align: left !important;
    width: 100% !important;
    margin: 0 !important;
}

/* ── Sidebar: aggressively tighten Streamlit's default top padding ── */
[data-testid="stSidebarHeader"] {
    padding: 0.25rem 0.75rem !important;
    min-height: unset !important;
    height: auto !important;
}
[data-testid="stSidebarContent"],
[data-testid="stSidebarUserContent"] { padding-top: 0 !important; }
section[data-testid="stSidebar"] > div { padding-top: 0 !important; }
[data-testid="stSidebarNav"] { margin-top: 0 !important; padding-top: 0 !important; }

/* ── Sidebar brand title (injected above st.navigation menu) ── */
[data-testid="stSidebarNav"]::before {
    content: "🚌 Smart Bus GPS";
    display: block;
    color: #0f172a;
    font-size: 1.2rem;
    font-weight: 800;
    letter-spacing: 0.02em;
    padding: 0 1rem 0.5rem;
    border-bottom: 1px solid rgba(127,127,127,0.25);
    margin: 0 0 0.25rem;
}

/* ── Metric cards ── */
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


# ── Page wrappers (each becomes a route) ───────────────────────────────────────
def _dashboard() -> None:
    render_dashboard_page(api_get, speed_color)


def _activity() -> None:
    render_activity_page(api_get, speed_color)


# ── Navigation (one URL per page) ──────────────────────────────────────────────
pages = [
    st.Page(_dashboard, title="Dashboard", icon="🚌", url_path="dashboard", default=True),
    st.Page(_activity,  title="Hoạt động", icon="📊", url_path="activity"),
]
nav = st.navigation(pages, position="sidebar")

# Run the page selected by st.navigation. Per-page sidebar widgets are added
# inside each render_*_page(). The "🚌 Smart Bus GPS" brand sits above the nav
# via CSS (::before on stSidebarNav), since st.sidebar content always renders
# below the menu.
nav.run()

with st.sidebar:
    st.markdown(
        "<div style='margin-top:0.75rem; padding:10px 14px; border-radius:8px; "
        "background:rgba(13,148,136,0.10); border:1px solid rgba(13,148,136,0.25); "
        "font-size:0.85rem; line-height:1.4; color:#0f172a;'>"
        "Trang web chuyên dụng tìm kiếm và theo dõi xe buýt thời gian thực."
        "</div>",
        unsafe_allow_html=True,
    )

st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#64748b; font-size:0.78rem; padding:8px 0'>"
    "Smart Bus GPS · Dashboard · Nền tảng: FastAPI + Elasticsearch + Streamlit · "
    "Dịch vụ: livebus · fuzzysearch · platesearch · routedetail · stats · "
    "nearby · activity"
    "</div>",
    unsafe_allow_html=True,
)
