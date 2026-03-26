import requests
import pandas as pd
import os
import time
import osmnx as ox
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, LineString, MultiLineString
from shapely.ops import unary_union
import matplotlib.pyplot as plt


def get_bus_data():
    pts = []
    try:
        kmb = requests.get("https://data.etabus.gov.hk/v1/transport/kmb/stop", timeout=20).json()['data']
        pts += [{'y': float(s['lat']), 'x': float(s['long'])} for s in kmb]
        ctb = requests.get("https://rt.data.gov.hk/v2/transport/citybus/stop/ctb", timeout=20).json()['data']
        pts += [{'y': float(s['lat']), 'x': float(s['long'])} for s in ctb]
        nlb = requests.get("https://rt.data.gov.hk/v2/transport/nlb/stop.php?action=list", timeout=20).json()['stops']
        pts += [{'y': float(s['lat']), 'x': float(s['lon'])} for s in nlb]
    except: pass
    df = pd.DataFrame(pts).drop_duplicates(subset=['x', 'y'])
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.x, df.y), crs="EPSG:4326")

def calc_iso(G, node, d=400):
    try:
        sub = nx.ego_graph(G, node, radius=d, distance='length')
        if len(sub.edges) > 0:
            lines = [data.get('geometry', LineString([(G.nodes[u]['x'], G.nodes[u]['y']), (G.nodes[v]['x'], G.nodes[v]['y'])])) 
                     for u, v, k, data in sub.edges(data=True, keys=True)]
            return MultiLineString(lines).buffer(0.0006)
    except: pass
    return None

#main 
print("="*50)
print("  HK TRANSIT ACCESSIBILITY MODEL v1.0")
print(f"  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print("="*50)

start_t = time.time()
stops = get_bus_data()
regions = ["Kowloon, Hong Kong", "Hong Kong Island, Hong Kong", "New Territories, Hong Kong"]
all_p = []
log_stats = []

for reg in regions:
    print(f"\n Analyzing {reg}...")
    try:
        b = ox.geocode_to_gdf(reg)
        G = ox.graph_from_place(reg, network_type='walk')
        G = ox.distance.add_edge_lengths(G)
        
        r_stops = gpd.sjoin(stops, b, predicate='within').copy()
        r_stops['node'] = ox.nearest_nodes(G, X=r_stops.x, Y=r_stops.y)
        
        isochrones = []
        for i, n in enumerate(r_stops['node']):
            isochrones.append(calc_iso(G, n))
            if (i + 1) % 500 == 0:
                print(f"  > Progress: {((i+1)/len(r_stops))*100:.1f}% ({i+1}/{len(r_stops)})")
        
        reg_union = unary_union([p for p in isochrones if p])
        final_poly = reg_union.intersection(b.geometry.iloc[0])
        all_p.append(final_poly)
        
       
        area_sqkm = final_poly.area * 10**10 # simplified area in square kilometers (approximation)
        rate = (final_poly.area / b.geometry.iloc[0].area) * 100
        log_stats.append({"Region": reg.split(',')[0], "Stops": len(r_stops), "Coverage": f"{rate:.2f}%"})
        
    except Exception as e:
        print(f"  ! Error: {e}")


if all_p:
    u_full = unary_union(all_p)
    outline = ox.geocode_to_gdf("Hong Kong")
    total_rate = (u_full.area / outline.geometry.iloc[0].area) * 100
    elapsed = (time.time() - start_t) / 60

    print("\n" + "="*50)
    print("  final report:")
    print("-" * 50)
    df_report = pd.DataFrame(log_stats)
    print(df_report.to_string(index=False))
    print("-" * 50)
    print(f"  whole HK coverage: {total_rate:.2f}%")
    print(f"  runtime:     {elapsed:.1f} min")
    print("="*50)


    fig, ax = plt.subplots(figsize=(16, 12))
    outline.plot(ax=ax, color='#f2f2f2', edgecolor='#333333', lw=0.5)
    gpd.GeoSeries([u_full]).plot(ax=ax, color='green', alpha=0.4, label='400m Buffer')
    stops.plot(ax=ax, color='red', markersize=0.1, alpha=0.2)
    ax.set_title(f"Pedestrian Accessibility Index: {total_rate:.2f}%", loc='left', fontsize=14)
    ax.set_axis_off()
    
    plt.savefig("HK_Bus_Final_Report.png", dpi=300, bbox_inches='tight')
    plt.show()