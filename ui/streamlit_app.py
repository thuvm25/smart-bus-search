import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="HCMC Bus GPS Search", layout="wide", page_icon="🚌")

import math

import pandas as pd
import pydeck as pdk

from api_client import (
    search_active,
    search_nearby,
    search_vehicle_trace,
    get_density,
    get_speed_stats,
    get_active_count,
    get_index_stats,
    get_realtime,
    run_benchmark,
)

# ─── Constants ───────────────────────────────────────────────────────

LIGHT_MAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
BUS_ICON_URL = "https://img.icons8.com/color/96/bus.png"
HCM_CENTER = (10.7769, 106.7009)


# ─── Helper functions ────────────────────────────────────────────────

def _speed_band(speed: float | None) -> str:
    if speed is None:
        return "Unknown"
    try:
        if isinstance(speed, float) and math.isnan(speed):
            return "Unknown"
    except Exception:
        return "Unknown"
    if speed > 50:
        return ">50 km/h"
    if speed >= 40:
        return "40-50 km/h"
    if speed >= 30:
        return "30-40 km/h"
    if speed >= 20:
        return "20-30 km/h"
    return "<20 km/h"


def _speed_color(speed: float | None) -> list[int]:
    if speed is None:
        return [130, 130, 130]
    try:
        if isinstance(speed, float) and math.isnan(speed):
            return [130, 130, 130]
    except Exception:
        return [130, 130, 130]
    if speed > 50:
        return [220, 40, 40]  # red
    if speed >= 40:
        return [245, 190, 55]  # yellow
    if speed >= 30:
        return [40, 130, 210]  # blue
    if speed >= 20:
        return [130, 130, 130]  # gray
    return [15, 15, 15]  # black


def _make_circle_polygon(lat: float, lon: float, radius_m: int, points: int = 72) -> list[list[float]]:
    lat_rad = math.radians(lat)
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = max(111_320.0 * math.cos(lat_rad), 1e-6)

    polygon: list[list[float]] = []
    for i in range(points + 1):
        theta = 2.0 * math.pi * i / points
        d_lat = (radius_m * math.sin(theta)) / meters_per_deg_lat
        d_lon = (radius_m * math.cos(theta)) / meters_per_deg_lon
        polygon.append([lon + d_lon, lat + d_lat])
    return polygon


def _zoom_for_radius(radius_m: int, lat: float) -> float:
    if radius_m <= 200:
        base_zoom = 15.5
    elif radius_m <= 400:
        base_zoom = 14.8
    elif radius_m <= 700:
        base_zoom = 14.2
    elif radius_m <= 1000:
        base_zoom = 13.8
    elif radius_m <= 1500:
        base_zoom = 13.3
    elif radius_m <= 2200:
        base_zoom = 12.9
    else:
        base_zoom = 12.5
    lat_factor = max(0.85, min(1.1, math.cos(math.radians(lat)) / 0.95))
    return max(10.5, min(16.5, base_zoom + (lat_factor - 1.0) * 0.8))


def _normalize_items(mode_name: str, payload: dict) -> pd.DataFrame:
    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not items:
        return pd.DataFrame()

    df = pd.DataFrame(items)

    if mode_name == "Nearby buses":
        if "x" in df.columns and "lon" not in df.columns:
            df["lon"] = df["x"]
        if "y" in df.columns and "lat" not in df.columns:
            df["lat"] = df["y"]

    if mode_name == "Vehicle trace" and isinstance(payload, dict):
        for key in ["vehicle", "mapping_route_no", "mapping_route_id", "route_name"]:
            if key in payload and key not in df.columns:
                df[key] = payload.get(key)

    return df


# ─── Render helpers ──────────────────────────────────────────────────

def _render_result_panel(mode_name: str, payload: dict, df: pd.DataFrame) -> None:
    st.subheader("🔍 Kết quả tìm kiếm")
    col_a, col_b = st.columns([2.2, 1.2])

    with col_a:
        st.metric("Số bản ghi", int(len(df)))
        if mode_name == "Nearby buses":
            total = int(payload.get("total", len(df)))
            returned = int(payload.get("returned", len(df)))
            limit = int(payload.get("limit", returned))
            st.write(f"Tìm thấy trong bán kính: **{total}**")
            st.write(f"Đang hiển thị: **{returned}** (giới hạn tối đa **{limit}**)")
        if mode_name == "Vehicle trace" and not df.empty:
            first = df.iloc[0].to_dict()
            route_label = first.get("route_name") or "N/A"
            stop_label = first.get("stop_name") or "N/A"
            st.write(f"Vehicle: `{first.get('vehicle', 'N/A')}`")
            st.write(f"Route: **{route_label}**")
            st.write(f"Điểm dừng gần nhất: **{stop_label}**")
        elif not df.empty:
            top_stops = (
                df["stop_name"].dropna().value_counts().head(3).index.tolist()
                if "stop_name" in df.columns
                else []
            )
            if top_stops:
                st.write("Top điểm dừng xuất hiện:")
                for name in top_stops:
                    st.write(f"- {name}")

    with col_b:
        st.markdown("**Gợi ý**")
        st.caption("Bật Auto refresh để theo dõi dữ liệu ingest realtime (khi simulator đang chạy).")


def _render_points_map(
    df: pd.DataFrame,
    center_lat: float | None = None,
    center_lon: float | None = None,
    radius_m: int | None = None,
    fixed_view: bool = True,
) -> None:
    # Avoid "jitter" on auto-refresh by keeping view state stable.
    # If fixed_view=True, center comes from user inputs (or HCM_CENTER), not from data mean.
    if fixed_view:
        map_center_lat = float(center_lat) if center_lat is not None else float(HCM_CENTER[0])
        map_center_lon = float(center_lon) if center_lon is not None else float(HCM_CENTER[1])
    else:
        map_center_lat = float(center_lat) if center_lat is not None else float(df["lat"].mean())
        map_center_lon = float(center_lon) if center_lon is not None else float(df["lon"].mean())

    zoom = _zoom_for_radius(int(radius_m), map_center_lat) if radius_m is not None else 11

    view_state = pdk.ViewState(
        latitude=map_center_lat,
        longitude=map_center_lon,
        zoom=zoom,
        pitch=0,
    )
    layers = []

    icon_df = df.copy()
    icon_df["icon_data"] = [
        {
            "url": BUS_ICON_URL,
            "width": 96,
            "height": 96,
            "anchorY": 96,
        }
    ] * len(icon_df)

    bus_icon_layer = pdk.Layer(
        "IconLayer",
        data=icon_df,
        get_icon="icon_data",
        get_position="[lon, lat]",
        get_size=4,
        size_scale=8,
        size_min_pixels=22,
        pickable=True,
    )
    layers.append(bus_icon_layer)

    if center_lat is not None and center_lon is not None:
        center_layer = pdk.Layer(
            "ScatterplotLayer",
            data=[{"lat": center_lat, "lon": center_lon}],
            get_position="[lon, lat]",
            get_fill_color=[220, 20, 60],
            get_radius=70,
            pickable=True,
            opacity=0.95,
        )
        layers.append(center_layer)

    if center_lat is not None and center_lon is not None and radius_m is not None:
        circle_polygon = _make_circle_polygon(float(center_lat), float(center_lon), int(radius_m))
        radius_layer = pdk.Layer(
            "PolygonLayer",
            data=[{"polygon": circle_polygon}],
            get_polygon="polygon",
            get_fill_color=[65, 105, 225, 30],
            get_line_color=[65, 105, 225, 220],
            line_width_min_pixels=2,
            stroked=True,
            filled=True,
            pickable=False,
        )
        layers.append(radius_layer)

    deck = pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style=LIGHT_MAP_STYLE,
        tooltip={"text": "Vehicle: {vehicle}\nRoute: {route_name}\nStop: {stop_name}\nSpeed: {speed}"},
    )
    st.pydeck_chart(deck, use_container_width=True)


def _render_trace_map(df: pd.DataFrame) -> None:
    if len(df) < 2:
        _render_points_map(df)
        return

    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6_371_000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return r * c

    segments: list[dict] = []
    ordered = df.copy()
    if "datetime" in ordered.columns:
        ordered["datetime"] = pd.to_datetime(ordered["datetime"], errors="coerce")
        ordered = ordered.sort_values("datetime")
    ordered = ordered.reset_index(drop=True)

    # Downsample very long traces to keep map readable.
    max_points = 2500
    if len(ordered) > max_points:
        step = max(1, len(ordered) // max_points)
        ordered = ordered.iloc[::step].reset_index(drop=True)

    # Break segments on outliers (GPS jump) / long gaps to avoid "fan" artifacts.
    max_jump_m = 1500.0
    max_gap_s = 8 * 60.0

    for i in range(len(ordered) - 1):
        a = ordered.iloc[i]
        b = ordered.iloc[i + 1]
        if pd.isna(a["lat"]) or pd.isna(a["lon"]) or pd.isna(b["lat"]) or pd.isna(b["lon"]):
            continue

        # Time gap (if datetime available)
        if "datetime" in ordered.columns and pd.notna(a.get("datetime")) and pd.notna(b.get("datetime")):
            dt_s = (b["datetime"] - a["datetime"]).total_seconds()
            if dt_s < 0 or dt_s > max_gap_s:
                continue

        dist_m = _haversine_m(float(a["lat"]), float(a["lon"]), float(b["lat"]), float(b["lon"]))
        if dist_m > max_jump_m:
            continue

        speed_val = a.get("speed")
        segments.append(
            {
                "path": [[float(a["lon"]), float(a["lat"])], [float(b["lon"]), float(b["lat"])]],
                "color": _speed_color(speed_val),
                "speed_band": _speed_band(speed_val),
                "speed": speed_val,
            }
        )

    point_layer = pdk.Layer(
        "ScatterplotLayer",
        data=ordered,
        get_position="[lon, lat]",
        get_fill_color="color",
        get_radius=18,
        pickable=True,
    )
    path_layer = pdk.Layer(
        "PathLayer",
        data=segments,
        get_path="path",
        get_color="color",
        width_min_pixels=4,
        pickable=True,
    )

    view_state = pdk.ViewState(
        latitude=float(ordered["lat"].mean()),
        longitude=float(ordered["lon"].mean()),
        zoom=12,
        pitch=25,
    )

    deck = pdk.Deck(
        layers=[path_layer, point_layer],
        initial_view_state=view_state,
        map_style=LIGHT_MAP_STYLE,
        tooltip={"text": "Speed band: {speed_band}\nSpeed: {speed}"},
    )
    st.pydeck_chart(deck, use_container_width=True)


# ─── Page: Search ────────────────────────────────────────────────────

def page_search():
    st.title("🚌 HCMC Bus Visual Search")
    st.caption("Tìm kiếm xe buýt theo vị trí, xem quỹ đạo, và theo dõi hoạt động real-time")

    # Realtime ingest status
    with st.container(border=True):
        st.markdown("**Realtime ingest (last 60s)**")
        try:
            rt = get_realtime(60)
            c1, c2 = st.columns(2)
            c1.metric("Records", f"{rt.get('records', 0):,}")
            c2.metric("Unique vehicles", f"{rt.get('unique_vehicles', 0):,}")
        except Exception as e:
            st.caption(f"Không lấy được realtime metrics: {e}")

    st.sidebar.header("Search Options")
    mode = st.sidebar.selectbox("Loại tìm kiếm", ["Active buses", "Nearby buses", "Vehicle trace"])

    auto_refresh_sec = st.sidebar.slider("Auto refresh (giây, 0 = tắt)", 0, 10, 3)
    # Auto refresh only for modes that make sense to update continuously.
    # Vehicle trace should not refresh automatically (would clear results / require re-run).
    if auto_refresh_sec > 0 and mode in ["Active buses", "Nearby buses"]:
        st_autorefresh(interval=auto_refresh_sec * 1000, key="auto_refresh_counter")

    payload: dict | None = None

    if mode == "Active buses":
        minutes = st.sidebar.slider("Hoạt động trong (phút, 0 = toàn bộ)", 0, 60, 0)
        manual_click = st.sidebar.button("Tìm kiếm")
        if auto_refresh_sec > 0 or manual_click:
            with st.spinner("Đang tìm xe buýt đang hoạt động..."):
                payload = search_active(minutes)

    elif mode == "Nearby buses":
        lat = st.sidebar.number_input("Latitude", value=10.7769, format="%.6f")
        lon = st.sidebar.number_input("Longitude", value=106.7009, format="%.6f")
        radius_m = st.sidebar.slider("Bán kính (m)", 100, 3000, 700, step=100)
        nearby_limit = st.sidebar.slider("Số bản ghi tối đa", 100, 2000, 1000, step=100)
        manual_click = st.sidebar.button("Tìm kiếm")
        if auto_refresh_sec > 0 or manual_click:
            with st.spinner("Đang tìm xe buýt gần đây..."):
                payload = search_nearby(lat, lon, radius_m, nearby_limit)

    elif mode == "Vehicle trace":
        vehicle_id = st.sidebar.text_input("Vehicle ID", "e738d8470a8d11a7a6d3dd7741f295c0dc3fd6779ed9d76ea7325fd1ee277891")
        minutes = st.sidebar.slider("Trace phút (0 = toàn bộ)", 0, 120, 0)
        if st.sidebar.button("Tìm kiếm"):
            with st.spinner("Đang lấy quỹ đạo xe..."):
                payload = search_vehicle_trace(vehicle_id, minutes)

    if payload:
        df = _normalize_items(mode, payload)

        if df.empty:
            st.warning("Không có kết quả hợp lệ để hiển thị.")
        else:
            if "speed" not in df.columns:
                df["speed"] = None
            df["color"] = df["speed"].apply(_speed_color)
            if "route_name" not in df.columns:
                df["route_name"] = None
            if "stop_name" not in df.columns:
                df["stop_name"] = None
            if "vehicle" not in df.columns:
                df["vehicle"] = None

            _render_result_panel(mode, payload, df)

            st.subheader("🗺️ Bản đồ")
            if "lat" in df.columns and "lon" in df.columns:
                if mode == "Vehicle trace":
                    _render_trace_map(df)
                elif mode == "Nearby buses":
                    _render_points_map(
                        df,
                        center_lat=float(payload.get("lat", lat if "lat" in locals() else df["lat"].mean())),
                        center_lon=float(payload.get("lon", lon if "lon" in locals() else df["lon"].mean())),
                        radius_m=int(payload.get("radius_m", radius_m if "radius_m" in locals() else 500)),
                        fixed_view=True,
                    )
                else:
                    _render_points_map(
                        df,
                        center_lat=HCM_CENTER[0],
                        center_lon=HCM_CENTER[1],
                        radius_m=None,
                        fixed_view=True,
                    )
            else:
                st.warning("Response không có cột lat/lon để vẽ bản đồ.")

            st.subheader("📊 Bảng dữ liệu")
            show_cols = [
                c
                for c in [
                    "vehicle",
                    "datetime",
                    "speed",
                    "ignition",
                    "route_name",
                    "stop_name",
                    "mapping_route_no",
                    "lat",
                    "lon",
                ]
                if c in df.columns
            ]
            st.dataframe(df[show_cols], use_container_width=True)
    else:
        st.info("Chọn loại tìm kiếm và bấm 'Tìm kiếm' để xem kết quả.")


# ─── Page: Analytics ─────────────────────────────────────────────────

def page_analytics():
    st.title("📈 Analytics Dashboard")
    st.caption("Thống kê và phân tích dữ liệu GPS xe buýt từ Elasticsearch")

    # Optional auto-refresh for dashboards
    a_col1, a_col2 = st.columns([1.2, 3.8])
    with a_col1:
        analytics_refresh = st.selectbox(
            "Auto refresh (Analytics)",
            [0, 5, 10, 15, 30],
            format_func=lambda x: "Tắt" if x == 0 else f"{x}s",
            key="analytics_refresh_sec",
        )
    with a_col2:
        st.caption("Bật để dashboard tự cập nhật (đặc biệt hữu ích khi simulator đang chạy).")
    if int(analytics_refresh) > 0:
        st_autorefresh(interval=int(analytics_refresh) * 1000, key="analytics_autorefresh_counter")

    # ── Index Stats ──
    st.subheader("📦 Thông tin Index")
    try:
        stats = get_index_stats()
        if stats:
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Tổng Documents", f"{stats.get('doc_count', 0):,}")
            c2.metric("Kích thước", f"{stats.get('size_mb', 0):.1f} MB")
            c3.metric("Tổng Indexing", f"{stats.get('indexing_total', 0):,}")
            c4.metric("Tổng Search", f"{stats.get('search_total', 0):,}")
            c5.metric("Size (bytes)", f"{stats.get('size_bytes', 0):,}")
        else:
            st.warning("Index chưa có dữ liệu hoặc chưa được tạo.")
    except Exception as e:
        st.error(f"Lỗi khi gọi API stats: {e}")

    st.divider()

    # ── Active Vehicle Count ──
    st.subheader("🚍 Xe buýt đang hoạt động")
    active_minutes = st.selectbox(
        "Khoảng thời gian",
        [5, 15, 30, 60],
        format_func=lambda x: f"{x} phút gần nhất",
        key="active_minutes",
    )
    try:
        active_data = get_active_count(active_minutes)
        ac1, ac2, ac3 = st.columns(3)
        ac1.metric("Số xe hoạt động", f"{active_data.get('active_vehicles', 0):,}")
        ac2.metric("Tổng bản ghi", f"{active_data.get('total_records', 0):,}")
        ac3.metric("Cửa sổ thời gian", f"{active_data.get('time_window_minutes', active_minutes)} phút")
    except Exception as e:
        st.error(f"Lỗi khi gọi API active-count: {e}")

    st.divider()

    # ── Speed Statistics ──
    st.subheader("🏎️ Thống kê tốc độ")
    speed_minutes = st.selectbox("Khoảng thời gian", [None, 5, 15, 30, 60], format_func=lambda x: "Toàn bộ" if x is None else f"{x} phút gần nhất")
    try:
        speed_data = get_speed_stats(speed_minutes)
        if speed_data and speed_data.get("count", 0) > 0:
            sc1, sc2, sc3, sc4, sc5 = st.columns(5)
            sc1.metric("Số bản ghi", f"{speed_data.get('count', 0):,}")
            sc2.metric("Tốc độ min", f"{speed_data.get('min', 0):.1f} km/h")
            sc3.metric("Tốc độ trung bình", f"{speed_data.get('avg', 0):.1f} km/h")
            sc4.metric("Tốc độ max", f"{speed_data.get('max', 0):.1f} km/h")
            sc5.metric("Độ lệch chuẩn", f"{speed_data.get('std_deviation', 0):.1f}")

            # Speed histogram chart
            histogram = speed_data.get("histogram", [])
            if histogram:
                hist_df = pd.DataFrame(histogram)
                st.bar_chart(hist_df.set_index("speed_range")["count"])
        else:
            st.info("Không có dữ liệu tốc độ.")
    except Exception as e:
        st.error(f"Lỗi khi gọi API speed: {e}")

    st.divider()

    # ── Density Heatmap ──
    st.subheader("🌡️ Bản đồ mật độ xe buýt")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        density_precision = st.slider("Geohash precision", 3, 8, 5, help="Cao hơn = ô nhỏ hơn. 5≈5km, 6≈1km, 7≈150m")
    with col_d2:
        density_minutes = st.selectbox("Thời gian (density)", [None, 5, 15, 30, 60],
                                        format_func=lambda x: "Toàn bộ" if x is None else f"{x} phút",
                                        key="density_time")

    try:
        density = get_density(precision=density_precision, minutes=density_minutes)
        cells = density.get("cells", [])
        if cells:
            st.write(f"Tổng số ô: **{density.get('total_cells', len(cells))}**")
            cell_df = pd.DataFrame(cells)

            # Color ramp for density (low -> high)
            counts = cell_df["doc_count"].fillna(0).astype(float)
            q1, q2, q3 = counts.quantile([0.25, 0.5, 0.75]).tolist()
            vmin, vmax = float(counts.min()), float(counts.max())

            def _density_color(v: float) -> list[int]:
                # 4 bins: very low, low, medium, high
                if v <= q1:
                    return [33, 102, 172, 120]   # blue
                if v <= q2:
                    return [103, 169, 207, 140]  # light blue
                if v <= q3:
                    return [253, 174, 97, 160]   # orange
                return [215, 48, 39, 190]        # red

            cell_df["color"] = counts.apply(_density_color)
            # Log-ish radius so high density pops but doesn't explode
            cell_df["radius"] = (counts.clip(lower=1) ** 0.6) * 120

            # Heatmap layer
            heatmap_layer = pdk.Layer(
                "HeatmapLayer",
                data=cell_df,
                get_position="[lon, lat]",
                get_weight="doc_count",
                radius_pixels=60,
                intensity=1,
                threshold=0.1,
            )

            # Scatterplot with size proportional to doc_count
            scatter_layer = pdk.Layer(
                "ScatterplotLayer",
                data=cell_df,
                get_position="[lon, lat]",
                get_fill_color="color",
                get_radius="radius",
                radius_min_pixels=5,
                radius_max_pixels=50,
                pickable=True,
            )

            view_state = pdk.ViewState(
                latitude=float(cell_df["lat"].mean()),
                longitude=float(cell_df["lon"].mean()),
                zoom=11,
                pitch=0,
            )
            deck = pdk.Deck(
                layers=[heatmap_layer, scatter_layer],
                initial_view_state=view_state,
                map_style=LIGHT_MAP_STYLE,
                tooltip={"text": "Geohash: {geohash}\nSố bản ghi: {doc_count}\nSố xe: {unique_vehicles}"},
            )
            st.pydeck_chart(deck, use_container_width=True)

            # Density legend (doc_count bins)
            st.markdown("**Legend (doc_count per cell)**")
            legend_cols = st.columns(4)
            bins = [
                (f"≤ {int(q1)}", [33, 102, 172]),
                (f"{int(q1)+1}–{int(q2)}", [103, 169, 207]),
                (f"{int(q2)+1}–{int(q3)}", [253, 174, 97]),
                (f"> {int(q3)}", [215, 48, 39]),
            ]
            for col, (label, rgb) in zip(legend_cols, bins):
                with col:
                    st.markdown(
                        f"<div style='display:flex;align-items:center;gap:10px'>"
                        f"<div style='width:18px;height:18px;border-radius:4px;background:rgb({rgb[0]},{rgb[1]},{rgb[2]});"
                        f"border:1px solid rgba(0,0,0,.15)'></div>"
                        f"<div style='font-size:14px'>{label}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
            st.caption(f"Min={int(vmin)} · Max={int(vmax)} (bin theo quartiles)")

            # Table of density data
            with st.expander("Xem dữ liệu mật độ chi tiết"):
                st.dataframe(cell_df[["geohash", "doc_count", "unique_vehicles", "lat", "lon"]], use_container_width=True)
        else:
            st.info("Không có dữ liệu density.")
    except Exception as e:
        st.error(f"Lỗi khi gọi API density: {e}")


def page_benchmark():
    st.title("⚡ Performance Benchmark")
    st.caption("Đánh giá hiệu năng Elasticsearch: indexing throughput, search latency, aggregation latency, scalability")

    st.info("Benchmark sẽ tạo một index tạm thời, chạy các bài test, và xóa sau khi hoàn thành.")

    if st.button("🚀 Chạy Benchmark", type="primary"):
        try:
            result = run_benchmark()
        except Exception as e:
            st.error(f"Không thể chạy benchmark: {e}")
            return

        # ── 1. Indexing throughput ──
        st.subheader("1️⃣ Indexing Throughput (10,000 documents)")
        ix_result = result.get("indexing", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Documents", f"{int(ix_result.get('documents', 0)):,}")
        c2.metric("Thời gian", f"{float(ix_result.get('elapsed_sec', 0)):.2f}s")
        c3.metric("Throughput", f"{float(ix_result.get('docs_per_sec', 0)):,.0f} docs/s")
        c4.metric("Errors", str(ix_result.get("errors", 0)))

        st.divider()

        # ── 2. Search latency ──
        st.subheader("2️⃣ Geo Search Latency (50 queries)")
        sl_result = result.get("search_latency", {})
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Min", f"{float(sl_result.get('min_ms', 0)):.2f} ms")
        c2.metric("Avg", f"{float(sl_result.get('avg_ms', 0)):.2f} ms")
        c3.metric("Median", f"{float(sl_result.get('median_ms', 0)):.2f} ms")
        c4.metric("P95", f"{float(sl_result.get('p95_ms', 0)):.2f} ms")
        c5.metric("Max", f"{float(sl_result.get('max_ms', 0)):.2f} ms")

        st.divider()

        # ── 3. Aggregation latency ──
        st.subheader("3️⃣ Aggregation Latency (30 queries)")
        al_result = result.get("aggregation_latency", {})
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Min", f"{float(al_result.get('min_ms', 0)):.2f} ms")
        c2.metric("Avg", f"{float(al_result.get('avg_ms', 0)):.2f} ms")
        c3.metric("Median", f"{float(al_result.get('median_ms', 0)):.2f} ms")
        c4.metric("P95", f"{float(al_result.get('p95_ms', 0)):.2f} ms")
        c5.metric("Max", f"{float(al_result.get('max_ms', 0)):.2f} ms")

        st.divider()

        # ── 4. Scalability ──
        st.subheader("4️⃣ Scalability Test")
        sc_results = result.get("scalability", [])
        sc_df = pd.DataFrame(sc_results)
        st.dataframe(sc_df, use_container_width=True)

        # Chart: throughput vs data volume
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.write("**Indexing Throughput vs Data Volume**")
            chart_df = sc_df.set_index("cumulative_docs")[["index_docs_per_sec"]]
            st.line_chart(chart_df)
        with col_chart2:
            st.write("**Search Latency vs Data Volume**")
            chart_df = sc_df.set_index("cumulative_docs")[["search_avg_ms", "search_p95_ms"]]
            st.line_chart(chart_df)

        st.success("✅ Benchmark hoàn thành! (Backend tự tạo & xóa index tạm.)")

    else:
        st.write("Nhấn nút **Chạy Benchmark** để bắt đầu đánh giá hiệu năng Elasticsearch.")

        st.subheader("Các bài test")
        st.markdown("""
        | # | Test | Mô tả |
        |---|------|-------|
        | 1 | **Indexing Throughput** | Bulk-index 10,000 documents, đo docs/second |
        | 2 | **Geo Search Latency** | 50 geo_distance queries, đo min/avg/p95/max |
        | 3 | **Aggregation Latency** | 30 geohash_grid aggregation queries |
        | 4 | **Scalability** | Tăng data volume 1k→5k→10k→25k docs, đo sự thay đổi |
        """)


# ─── Main Navigation ─────────────────────────────────────────────────

page = st.sidebar.radio(
    "📌 Chọn trang",
    ["🔍 Search", "📈 Analytics", "⚡ Benchmark"],
    key="nav_page",
)

if page == "🔍 Search":
    page_search()
elif page == "📈 Analytics":
    page_analytics()
elif page == "⚡ Benchmark":
    page_benchmark()