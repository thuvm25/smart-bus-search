"""
Smart Bus GPS — Streamlit Dashboard
Real-time visualization of bus GPS data via the FastAPI backend.

Run:
    streamlit run ui/smartsearchbus_web.py

Each sidebar tab is a real page with its own URL:
    /dashboard   — live map + fuzzy search
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
from nearby_page import render_nearby_page

# ── Config ─────────────────────────────────────────────────────────────────────
API_BASE = os.getenv("API_BASE", "http://localhost:8000")

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

/* ── Sidebar brand title (injected above st.navigation menu) ── */
[data-testid="stSidebarNav"]::before {
    content: "🚌 Smart Bus GPS";
    display: block;
    color: #e6edf3;
    font-size: 1.4rem;
    font-weight: 800;
    letter-spacing: 0.02em;
    padding: 1.25rem 1.5rem 0.75rem;
    border-bottom: 1px solid #30363d;
    margin-bottom: 0.5rem;
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


# ── Page wrappers (each becomes a route) ───────────────────────────────────────
def _dashboard() -> None:
    render_dashboard_page(api_get, speed_color)


def _nearby() -> None:
    render_nearby_page(api_get, speed_color)


def _activity() -> None:
    render_activity_page(api_get, speed_color)


# ── Navigation (one URL per page) ──────────────────────────────────────────────
pages = [
    st.Page(_dashboard, title="Dashboard",   icon="🚌", url_path="dashboard", default=True),
    st.Page(_nearby,    title="Tìm gần tôi", icon="📌", url_path="nearby"),
    st.Page(_activity,  title="Hoạt động",   icon="📊", url_path="activity"),
]
nav = st.navigation(pages, position="sidebar")

# Run the page selected by st.navigation. Per-page sidebar widgets (e.g. the
# Dashboard's auto-refresh checkbox) are added inside each render_*_page().
# The "🚌 Smart Bus GPS" brand sits above the nav via CSS (::before on
# stSidebarNav), since st.sidebar content always renders below the menu.
nav.run()

with st.sidebar:
    st.markdown("---")
    st.info("Trang web chuyên dụng tìm kiếm và theo dõi xe buýt thời gian thực.")

st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#8b949e; font-size:0.78rem; padding:8px 0'>"
    "Smart Bus GPS Dashboard · Powered by FastAPI + Elasticsearch + Streamlit"
    "</div>",
    unsafe_allow_html=True,
)
