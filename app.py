import streamlit as st
import pandas as pd
import folium
import geopandas as gpd
from streamlit_folium import st_folium
from data_parser import load_adjacency, load_geometries, load_trips, read_manhattan_ids, load_manhattan_zones, parse_to_ids, check_contiguity

st.set_page_config(page_title="Urban Flow Dashboard", layout="wide")

#Loading the data (with caching)
@st.cache_data
def load_all_data():
    trips_df = load_trips("data/taxi-trips.txt")
    adjacent_df = load_adjacency("data/adj_taxi.txt")
    geometry_df = load_geometries("data/nyc_taxi_zones.geojson")
    manhattan_ids_int = read_manhattan_ids()

    if not manhattan_ids_int:
        manhattan_df = load_manhattan_zones("data/manhattan-query.txt")
        fallback_ids = []

        item_to_process = manhattan_df if isinstance(manhattan_df, tuple) else [manhattan_df]
        for item in item_to_process:
            fallback_ids.extend(parse_to_ids(item))
        manhattan_ids_int = list(dict.fromkeys(fallback_ids))
    
    return trips_df, geometry_df, adjacent_df, manhattan_ids_int

trips_df, geometry_df, adjacent_df, manhattan_ids_int = load_all_data()

#Processing the geometry (with caching)
@st.cache_data
def process_geometry(_geometry_df, manhattan_ids_int):
    if "locationid" in _geometry_df.columns:
        geometry_df = _geometry_df.dropna(subset=["locationid"])
        geometry_df["locationid"] = geometry_df["locationid"].apply(
            lambda x: int(float(str(x).strip())) if str(x).strip() else -1
        )
        manhattan_gdf = geometry_df[geometry_df["locationid"].isin(manhattan_ids_int)] if manhattan_ids_int else gpd.GeoDataFrame()
    
    else:
        manhattan_gdf = gpd.GeoDataFrame()
    return manhattan_gdf
manhattan_gdf = process_geometry(geometry_df, manhattan_ids_int)

#Sidebar functions
st.sidebar.header("Filter patterns")
selected_origin = st.sidebar.selectbox("Select Origin Region", sorted(trips_df["origin"].unique()))

st.sidebar.subheader("Destination Filter")
destination_filter_mode = st.sidebar.radio(
    "Filter Mode",
    ["Show all destinations", "Filter by a specific destination"],
    help = "Choose whether you want to see all flows or you want to focus on a specific destination"
)

if destination_filter_mode == "Filter by a specific destination":
    selected_destination = st.sidebar.selectbox(
        "Select destination zone",
        sorted(trips_df["destination"].unique()),
        help = "Only shows the flows going to a particular destination"
    )

else:
    selected_destination = None

selected_time = st.sidebar.slider("Select time period", int(trips_df["time"].min()), int(trips_df["time"].max()))
support_threshold = st.sidebar.number_input("Support threshold", min_value=1, value = 5)

#Multi selection 
st.sidebar.divider()
st.sidebar.header("Multi zone selection")
enable_multi = st.sidebar.checkbox("Enable Multi zone selection", value = False)

if enable_multi:
    st.sidebar.warning("Click multiple zone to create a region")
    if "selected_zones" not in st.session_state:
        st.session_state["selected_zones"] = []
    
    if st.session_state["selected_zones"]:
        st.sidebar.write(f"**Selected zones:** {len(st.session_state['selected_zones'])}")
        st.sidebar.write(f"IDs: {st.session_state["selected_zones"]}")

        if st.sidebar.button("Clear selection"):
            st.session_state["selected_zones"] = []
            st.rerun()

        if check_contiguity(st.session_state["selected_zones"], adjacent_df):
            st.sidebar.success("Zones are contiguous")
        else:
            st.sidebar.error("Zones are not contiguous")
    else:
        st.sidebar.info("Click zones on the map to add them to your region")

#Main content
st.title("Urban Flow: Visualizing ODT flow Patterns")

filtered_trips = trips_df[
    (trips_df["origin"] == selected_origin) &
    (trips_df["trip_count"] >= support_threshold)
]

st.subheader("Raw Filtered Trip Data")
st.dataframe(filtered_trips)

#Layout under 'Raw filtered trip data'
col1, col2 = st.columns([2,1])

#Left column - map
with col1:
    st.subheader("Spatial pattern map") 
    m = folium.Map(location=[40.7831, -73.9712], zoom_start=11, tiles="CartoDB positron")

    if not manhattan_gdf.empty:
        try:
            plot_df = manhattan_gdf[["geometry", "locationid", "zone", "borough"]].copy()
            folium.GeoJson(
                plot_df,
                name = "Manhattan query region",
                style_function=lambda x: {"fillColor": "#3186cc", "color": "blue", "weight": 1, "fillOpacity": 0.3},
                highlight_function=lambda x: {"fillColor": "#ff0000", "color": "red", "weight": 2, "fillOpacity": 0.5},
                tooltip = folium.GeoJsonTooltip(
                    fields = ["zone", "locationid", "borough"],
                    aliases = ["Zone:", "ID:", "Borough:"],
                    localize = True
                )
            ).add_to(m)
        
        except:
            for _,row in manhattan_gdf.iterrows():
                if row.geometry:
                    folium.GeoJson(
                        row.geometry.__geo_interface__,
                        style_function=lambda x: {"fillColor": "#3186cc", "color": "blue", "weight": 1, "fillOpacity": 0.3}
                    ).add_to(m)
    
    else:
        st.warning("No Manhattan zones found")

    map_data = st_folium(m, width = 700, height = 500)

with col2:
    st.subheader("Active Metrics")
    st.write(f"Total Manhattan query zones loaded: {len(manhattan_ids_int)}")