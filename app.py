import streamlit as st
import pandas as pd
from data_parser import load_adjacency, load_geometries, load_trips

st.set_page_config(page_title="Urban Flow Dashboard", layout="wide")

#Loading the data (with caching)
@st.cache_data
def load_all_data():
    trips_df = load_trips("data/taxi-trips.txt")
    adjacent_df = load_adjacency("data/adj_taxi.txt")
    geometry_df = load_geometries("data/nyc_taxi_zones.geojson")
    
    return trips_df, geometry_df, adjacent_df

trips_df, geometry_df, adjacent_df = load_all_data()

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