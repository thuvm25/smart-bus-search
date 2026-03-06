import streamlit as st

st.set_page_config(page_title="HCMC Bus GPS Search", layout="wide")

import pandas as pd
import pydeck as pdk

from api_client import (
    search_active,
    search_nearby,
    search_vehicle_trace,
)

st.title("🚌 HCMC Bus GPS Search")

st.sidebar.header("Search Options")

mode = st.sidebar.selectbox(
    "Choose search type",
    ["Active buses", "Nearby buses", "Vehicle trace"]
)

data = None

# ----------------------------
# ACTIVE BUSES
# ----------------------------
if mode == "Active buses":

    minutes = st.sidebar.slider(
        "Active in last (minutes)",
        1,
        60,
        10
    )

    if st.sidebar.button("Search"):

        with st.spinner("Fetching active buses..."):
            data = search_active(minutes)

# ----------------------------
# NEARBY SEARCH
# ----------------------------
elif mode == "Nearby buses":

    lat = st.sidebar.number_input(
        "Latitude",
        value=10.7769
    )

    lon = st.sidebar.number_input(
        "Longitude",
        value=106.7009
    )

    radius_m = st.sidebar.slider(
        "Radius (meters)",
        100,
        2000,
        500
    )

    minutes = st.sidebar.slider(
        "Recent minutes",
        1,
        60,
        10
    )

    if st.sidebar.button("Search"):

        with st.spinner("Searching nearby buses..."):
            data = search_nearby(lat, lon, radius_m, minutes)

# ----------------------------
# VEHICLE TRACE
# ----------------------------
elif mode == "Vehicle trace":

    vehicle_id = st.sidebar.text_input(
        "Vehicle ID",
        "51B12345"
    )

    minutes = st.sidebar.slider(
        "Trace minutes",
        1,
        120,
        30
    )

    if st.sidebar.button("Search"):

        with st.spinner("Fetching vehicle trace..."):
            data = search_vehicle_trace(vehicle_id, minutes)

# ----------------------------
# DISPLAY RESULTS
# ----------------------------

if data:

    df = pd.DataFrame(data)

    st.subheader("Results")

    st.write(f"Total records: {len(df)}")

    st.dataframe(df)

    if "lat" in df.columns and "lon" in df.columns:

        st.subheader("Map")

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position="[lon, lat]",
            get_radius=50,
            pickable=True,
        )

        view_state = pdk.ViewState(
            latitude=df["lat"].mean(),
            longitude=df["lon"].mean(),
            zoom=12,
        )

        deck = pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip={"text": "Vehicle: {vehicle_id}"},
        )

        st.pydeck_chart(deck)

else:
    st.info("Run a search from the sidebar.")