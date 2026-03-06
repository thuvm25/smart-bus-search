from typing import Any

import pandas as pd
import streamlit as st


def render_map(items: list[dict[str, Any]]) -> None:
    if not items:
        st.info("Chưa có dữ liệu để hiển thị trên bản đồ.")
        return

    rows = []
    for item in items:
        src = item.get("_source", item)
        loc = src.get("location") or {}
        lat = loc.get("lat")
        lon = loc.get("lon")
        if lat is None or lon is None:
            continue
        rows.append({"lat": lat, "lon": lon})

    if not rows:
        st.info("Không tìm thấy điểm hợp lệ để hiển thị.")
        return

    df = pd.DataFrame(rows)
    st.map(df)

