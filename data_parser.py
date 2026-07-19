import geopandas as gpd
import pandas as pd
import re


def load_trips(filepath):
    data = []
    with open(filepath, "r") as f:
        for line in f:
            parts = re.split(r'\s+', line.strip())
            if len(parts)>=4:
                try:
                    data.append([int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])])
                except ValueError:
                    continue
    return pd.DataFrame(data, columns=["origin", "destination", "time", "trip_count"])


def load_adjacency(filepath):
    data = []
    with open(filepath, "r") as f:
        for line in f:
            parts = re.split(f'\s+', line.strip())
            if len(parts)>=2:
                try:
                    data.append([int(parts[0]), int(parts[1])])
                except ValueError:
                    continue
    return pd.DataFrame(data, columns=["Zone_A", "Zone_B"])


def load_geometries(filepath):
    gdf = gpd.read_file(filepath)
    gdf["locationid"] = gdf["locationid"].astype(int)
    if gdf.crs != "ESPG:4326":
        gdf = gdf.to_crs(epsg=4326)
    return gdf




    


