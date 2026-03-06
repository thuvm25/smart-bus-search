from typing import Any

import pandas as pd
import streamlit as st


def render_table(items: list[dict[str, Any]]) -> None:
    if not items:
        st.info("Không có bản ghi nào.")
        return

    rows = []
    for item in items:
        src = item.get("_source", item)
        rows.append(
            {
                "vehicle": src.get("vehicle"),
                "datetime": src.get("datetime"),
                "ignition": src.get("ignition"),
                "heading": src.get("heading"),
                "aircon": src.get("aircon"),
                "door_up": src.get("door_up"),
                "door_down": src.get("door_down"),
                "route_name": src.get("route_name"),
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df)

