from typing import Any

import pandas as pd
import streamlit as st


def render_table(items: list[dict[str, Any]]) -> None:
    if not items:
        st.info("Không có bản ghi nào.")
        return

    display_cols = [
        "vehicle", "datetime", "speed", "ignition", "heading",
        "aircon", "door_up", "door_down", "route_id", "route_no",
        "route_name", "stop_name", "lat", "lon",
    ]

    rows = []
    for item in items:
        row = {}
        for col in display_cols:
            row[col] = item.get(col)
        rows.append(row)

    df = pd.DataFrame(rows)
    present_cols = [c for c in display_cols if c in df.columns and df[c].notna().any()]
    st.dataframe(df[present_cols] if present_cols else df, use_container_width=True)
