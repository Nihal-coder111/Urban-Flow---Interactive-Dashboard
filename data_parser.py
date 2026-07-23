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


def read_manhattan_ids():
    try:
        with open("data/nyc_taxi_zones.geojson", "r") as f:
            content = f.read()
            ids = []
            for part in re.split(r'[\s,\n]+', content.strip()):
                if part:
                    try:
                        ids.append(int(float(part)))
                    except:
                        pass
            return list(dict.fromkeys(ids))
    except:
        pass

def load_manhattan_zones(filepath):
    with open(filepath, "r") as f:
        return f.read()

def parse_to_ids(item):
    if isinstance(item, (list, tuple)):
        item = ".".join(str(i) for i in item)

    ids = []
    for part in re.split(r'[\s,\n]+', str(item).strip()):
        if part:
            try:
                ids.append(int(float(part)))
            except ValueError:
                pass
    return ids


def check_contiguity(zone_ids, adjacency_df):
    if len(zone_ids) <= 1:
        return True

    adj_set = set()
    for _, row in adjacency_df.iterrows():
        adj_set.add((row["Zone_A"], row["Zone_B"]))
        adj_set.add((row["Zone_B"], row["Zone_A"]))

    connected = {zone_ids[0]}
    remaining = set(zone_ids[1:])

    changed = True
    while changed and remaining:
        changed = False
        for zone in list(remaining):
            for connected_zone in connected:
                if (zone, connected_zone) in adj_set:
                    connected.add(zone)
                    remaining.remove(zone)
                    changed = True
                    break
    
    return len(remaining) == 0

    


