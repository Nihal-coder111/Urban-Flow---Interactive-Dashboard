import streamlit as st
import pandas as pd
import folium
import geopandas as gpd
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
import time
from data_parser import load_adjacency, load_geometries, load_trips, read_manhattan_ids, load_manhattan_zones, parse_to_ids, check_contiguity, get_merged_centroids, get_zone_centroid

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

    #Flow logic
    if "clicked_zone_id" not in st.session_state:
        st.session_state["clicked_zone_id"] = None

    if enable_multi and st.session_state.get("selected_zones", []):
        zone_ids = st.session_state["selected_zones"]
        is_multi = True
    else:
        zone_ids = [st.session_state.get("clicked_zone_id")] if st.session_state.get("clicked_zone_id") else []
        is_multi = False

    valid_zones = [i for i in zone_ids if i is not None and i in geometry_df["locationid"].values]

    active_flows = pd.DataFrame()
    origin_centroid = None
    clicked_id = None
    selected_flow_details = None

    if valid_zones:
        if is_multi and len(valid_zones) > 1:
            if check_contiguity(valid_zones, adjacent_df):
                st.info(f"Region: {len(valid_zones)} contiguous zones: {valid_zones}")
                origin_centroid = get_merged_centroids(valid_zones, geometry_df)

                if origin_centroid:
                    merged_flow = []
                    for i in valid_zones:
                        zone_flow = trips_df[
                            (trips_df["origin"] == i) &
                            (trips_df["time"] == selected_time) &
                            (trips_df["trip_count"] >= support_threshold)
                        ]
                        
                        if not zone_flow.empty:
                            merged_flow.append(zone_flow)
                    active_flows = pd.concat(merged_flow, ignore_index=True) if merged_flow else pd.DataFrame

                    #destination filter
                    if selected_destination and not active_flows.empty:
                        active_flows = active_flows[active_flows["destination"] == selected_destination]
                    if not active_flows.empty:
                        if selected_destination:
                            st.info(f"Showing flow zones to {selected_destination} only")

                        flow_groups = active_flows.groupby("destination")["trip_count"].sum().reset_index()
                        max_trips = flow_groups["trip_count"].max()

                        for _, row in flow_groups.iterrows():
                            dest_id = row["destination"]
                            trip_count = row["trip_count"]
                            dest_centroid = get_zone_centroid(dest_id, geometry_df)
                        
                        if dest_centroid:
                            weight = 1 + (trip_count/max_trips)*4
                            color = "#FF0000" if trip_count > 20 else "#FF8800" if trip_count > 10 else "#3388FF"

                            folium.PolyLine(
                                [[origin_centroid[0], origin_centroid[1]], 
                                [dest_centroid[0], dest_centroid[1]]],
                                weight=weight,
                                color=color,
                                opacity=0.7,
                                tooltip=f"Region → Zone {dest_id}: {trip_count} trips"
                            ).add_to(m)

                        st.info(f"Showing {len(flow_groups)} regional flow patterns")
                    else:
                        if selected_destination:
                            st.info(f"No flow zones to Zone {selected_destination} at time {selected_time}")
                        else:
                            st.info(f"No regional flows at time {selected_time} ")
                else:
                    st.warning("Could not calculate region centroid")
            else:
                st.warning(f"Selected zones are not contiguous: {valid_zones}")
        else:
            clicked_id = valid_zones[0]
            origin_centroid = get_zone_centroid(clicked_id, geometry_df)

            if origin_centroid:
                active_flows = trips_df[
                    (trips_df["origin"] == clicked_id) &
                    (trips_df["time"] == selected_time) &
                    (trips_df["trip_count"] >= support_threshold)
                ]

                #The destination filter
                if selected_destination and not active_flows.empty:
                    active_flows = active_flows[active_flows["destination"] == selected_destination]

                if not active_flows.empty:
                    if selected_destination:
                        st.info(f"Showing flow zones to Zone {selected_destination} only")

                    flow_groups = active_flows.groupby("destination")["trip_count"].sum().reset_index()
                    max_trips = flow_groups["trip_count"].max()

                    for _, row in flow_groups.iterrows():
                        dest_id = row["destination"]
                        trip_count = row["trip_count"]
                        if dest_id == clicked_id:
                            continue

                        dest_centroid = get_zone_centroid(dest_id, geometry_df)
                        if dest_centroid:
                            weight = 1 + (trip_count / max_trips) * 4
                            color = '#FF0000' if trip_count > 20 else '#FF8800' if trip_count > 10 else '#3388FF'
                            
                            folium.PolyLine(
                                [[origin_centroid[0], origin_centroid[1]], 
                                 [dest_centroid[0], dest_centroid[1]]],
                                weight=weight,
                                color=color,
                                opacity=0.7,
                                tooltip=f"Zone {clicked_id} → Zone {dest_id}: {trip_count} trips"
                            ).add_to(m)
                    st.info(f"Showing {len(flow_groups)} flow patterns from zone {clicked_id}")

                else:
                    if selected_destination:
                        st.info(f"no flow from Zone {clicked_id} to Zone {selected_destination} at time {selected_time}")
                    else:
                        st.info(f"No flow from Zone {clicked_id} at time {selected_time}")
            else:
                st.warning(f"Could not find centroid for zone {clicked_id}")
    else:
        if selected_origin and selected_origin in geometry_df["locationid"].values:
            preview = trips_df[
                (trips_df['origin'] == selected_origin) & 
                (trips_df['time'] == selected_time) & 
                (trips_df['trip_count'] >= support_threshold)
            ]
            if not preview.empty:
                if not enable_multi:
                    st.info(f"Click a zone on the map to see flows. Preview: {len(preview)} flows from zone {selected_origin}")
                else:
                    st.info(f"Click zones on the map to build a region")
    #Heatmap
    show_heatmap = st.checkbox("Show destination heatmap", value=False)

    if show_heatmap:
        try:
            from folium.plugins import HeatMap
            heatmap_data = []

            if not active_flows.empty:
                data_source = active_flows

            else:
                data_source = trips_df[trips_df["trip_count"] >= support_threshold]

            if not data_source.empty:
                dest_aggregated = data_source.groupby("destination")["trip_count"].sum().reset_index()

                for _, row in dest_aggregated.iterrows():
                    dest_id = row["destination"]
                    trip_count = row["trip_count"]

                    centroid = get_zone_centroid(dest_id, geometry_df)
                    if centroid:
                        heatmap_data.append([centroid[0], centroid[1], int(trip_count)])
            if heatmap_data:
                HeatMap(
                    heatmap_data, 
                    radius=15, 
                    blur=20, 
                    min_opacity=0.3,
                    max_zoom=13
                ).add_to(m)
                st.success(f"🔥 Showing {len(heatmap_data)} destination hotspots")
            else:
                st.info("ℹ️ No data for heatmap. Try selecting a zone or changing time.")
                
        except ImportError:
            st.warning("⚠️ HeatMap plugin not available")
        except Exception as e:
            st.warning(f"⚠️ Could not load heatmap: {e}")
    map_data = st_folium(m, width=700, height=500, key="nyc_base_map")
    
    if map_data and map_data.get("last_active_drawing"):
        props = map_data["last_active_drawing"].get("properties")
        if props:
            new_id = props.get("locationid") or props.get("LocationID")
            if new_id:
                try:
                    new_id = int(new_id)
                    if enable_multi:
                        if "selected_zones" not in st.session_state:
                            st.session_state["selected_zones"] = []
                        if new_id in st.session_state["selected_zones"]:
                            st.session_state["selected_zones"].remove(new_id)
                        else:
                            st.session_state["selected_zones"].append(new_id)
                        st.rerun()
                    else:
                        if new_id != st.session_state.get("clicked_zone_id"):
                            st.session_state["clicked_zone_id"] = new_id
                            st.rerun()
                except:
                    pass
    

with col2:
    st.subheader("Active Metrics")
    st.write(f"Total Manhattan query zones loaded: {len(manhattan_ids_int)}")

    if not manhattan_gdf.empty:
        st.write(f"Zones on the map: {len(manhattan_gdf)}")

    if manhattan_ids_int:
        ids_str = ", ".join(str(id) for id in manhattan_ids_int[:10])
        if len(manhattan_ids_int) > 10:
            ids_str += f" ... (+{len(manhattan_ids_int) - 10} more)"
        st.write(f"**Zone IDs:** {ids_str}")

    st.divider()
    st.subheader("Zone interaction")

    #Single zone mode
    if not enable_multi and clicked_id:
        st.success(f"Selected Zone: **{clicked_id}** ")

        if not manhattan_gdf.empty:
            zone_info = manhattan_gdf[manhattan_gdf["locationid"] == clicked_id]
            if not zone_info.empty:
                if "zone" in zone_info.columns:
                    st.write(f"**Zone Name:** {zone_info.iloc[0]["zone"]}")
                if "borough" in zone_info.columns:
                    st.write(f"**Borough:** {zone_info.iloc[0]["borough"]}")

        st.divider()
        st.subheader("Flow patterns")
        st.write(f"**Time:** {selected_time}:00")
        st.write(f"**Support:** >= {support_threshold} trips")
        st.write(f"**Active flows:** {len(active_flows)} destinations")

        if not active_flows.empty:
            top_dests = active_flows.groupby("destination")["trip_count"].sum().reset_index()
            top_dests = top_dests.sort_values("trip_count", ascending=False).head(5)

            st.write("**Top 5 destinations**")
            for _,row in top_dests.iterrows():
                dest_id = row["destination"]
                trip_count = row["trip_count"]
                dest_info = manhattan_gdf[manhattan_gdf["locationid"] == dest_id]
                if not dest_info.empty and "zone" in dest_info.columns:
                    st.write(f"  • Zone {dest_id} ({dest_info.iloc[0]['zone']}): {trip_count} trips")
                else:
                    st.write(f"  • Zone {dest_id}: {trip_count} trips")

            #The plotly chart
            st.subheader("Top destinations")
            top_flows = active_flows.groupby("destination")["trip_count"].sum().reset_index()
            top_flows = top_flows.sort_values("trip_count", ascending=False).head(10)
            top_flows["destination"] = top_flows["destination"].astype(str)
            top_flows["zone_name"] = top_flows["destination"].apply(
                lambda x: manhattan_gdf[manhattan_gdf["locationid"] == int(x)]["zone"].iloc[0]
                if int(x) in manhattan_gdf["locationid"].values else "Unknown"
            )

            fig = px.bar(
                top_flows,
                x="destination",
                y="trip_count",
                labels={"destination": "Destination Zone", "trip_count": "Total trips"},
                color="trip_count",
                color_continuous_scale="Reds",
                title="Top 10 Destinations"
            )
            fig.update_layout(
                margin=dict(l=0, r=0, t=40, b=0),
                height=300,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color='white')
            )
            fig.update_traces(
                hovertemplate='Zone %{x}<br>Trips: %{y}<br>Zone Name: %{customdata}<extra></extra>',
                customdata=top_flows['zone_name']
            )

            st.plotly_chart(fig, use_container_width=True, key = f"flow_chart_{clicked_id}_{selected_time}_{time.time()}")

        #Adjacent zones
        if not adjacent_df.empty:
            st.divider()
            st.subheader("Adjacent zones")
            neighbors = adjacent_df[
                (adjacent_df["Zone_A"] == clicked_id) | (adjacent_df["Zone_B"] == clicked_id)
            ]
            neighbor_ids = list(set(neighbors["Zone_A"].to_list() + neighbors["Zone_B"].to_list()))
            if clicked_id in neighbor_ids:
                neighbor_ids.remove(clicked_id)

            if neighbor_ids:
                display = []
                for n_id in neighbor_ids:
                    n_info = manhattan_gdf[manhattan_gdf["locationid"] == n_id]
                    if not n_info.empty and "zone" in n_info.columns:
                        display.append(f"{n_id} ({n_info.iloc[0]["zone"]})")
                    else:
                        display.append(str(n_id))

                if len(neighbor_ids) > 5:
                    display.append(f"... +{len(neighbor_ids) - 5} more")
                st.write(f"**Neighbors ({len(neighbor_ids)}):** {', '.join(display)}")
            else:
                st.info("No adjacent neighbors")