from typing import Any

import pandas as pd
import streamlit as st


def render_map(items: list[dict[str, Any]]) -> None:
    if not items:
        st.info("Chưa có dữ liệu để hiển thị trên bản đồ.")
        return

    rows = []
    for item in items:
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            loc = item.get("location") or {}
            lat = lat or loc.get("lat")
            lon = lon or loc.get("lon")
        if lat is None or lon is None:
            continue
        rows.append({"lat": lat, "lon": lon})

    if not rows:
        st.info("Không tìm thấy điểm hợp lệ để hiển thị.")
        return

    df = pd.DataFrame(rows)
    st.map(df)
