import streamlit as st


def render_filters() -> tuple[float, float, int]:
    st.sidebar.header("Bộ lọc tìm kiếm")
    lat = st.sidebar.number_input("Latitude", value=10.776889, format="%.6f")
    lon = st.sidebar.number_input("Longitude", value=106.700806, format="%.6f")
    radius_km = st.sidebar.slider("Bán kính (km)", min_value=0.1, max_value=5.0, value=0.5, step=0.1)
    radius_m = int(radius_km * 1000)
    return lat, lon, radius_m

