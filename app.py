import streamlit as st
import pandas as pd
from data_parser import load_adjacency, load_geometries, load_trips

st.set_page_config(page_title="Urban Flow Dashboard", layout="wide")

#Loading the data (with caching)
st.cache_data
def load_all_function():
    trips_df = load_trips("data/taxi-trips.txt")
    adjacent_df = load_adjacency("data/adj_taxi.txt")
    geometry_df = load_geometries("data/nyc_taxi_zone.geojson")
    
    return trips_df, geometry_df, adjacent_df

trips_df, adjacent_df, geometry_df = load_all_function


