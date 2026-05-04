import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import os
import h3
from shapely.geometry import Polygon

# Rutas de los datos reales provistos
GFW_DIR = "/home/gorops/proyectos antigravity/ocean_proto/d1f2dc60-3841-11f1-bbe6-bfd704486e22"
OBIS_FILE = "/home/gorops/proyectos antigravity/ocean_proto/dwca-zd_594_1deg-v1.0/occurrence.txt"
OUTPUT_GEOJSON = "data/risk_hotspots.geojson"

# Bounding box constraints: Gulf of Mexico / Caribbean (where OBIS has data)
MIN_LAT, MAX_LAT = 15.0, 30.0
MIN_LON, MAX_LON = -98.0, -80.0
H3_RESOLUTION = 7

def get_h3_index(lat: float, lon: float, resolution: int) -> str:
    return h3.latlng_to_cell(lat, lon, resolution)

def cell_to_polygon(hex_id: str) -> Polygon:
    boundary = h3.cell_to_boundary(hex_id)
    # Convert from (lat, lng) to (lng, lat) for Shapely
    lng_lat_boundary = [(lng, lat) for lat, lng in boundary]
    return Polygon(lng_lat_boundary)

def run():
    print("Cargando datos reales de OBIS (Darwin Core Archive)...")
    # OBIS data is TSV
    df_obis = pd.read_csv(OBIS_FILE, sep='\t', low_memory=False)
    # Filtrar Bounding Box OBIS
    if 'decimalLatitude' in df_obis.columns and 'decimalLongitude' in df_obis.columns:
        df_obis = df_obis[
            (df_obis['decimalLatitude'] >= MIN_LAT) & (df_obis['decimalLatitude'] <= MAX_LAT) &
            (df_obis['decimalLongitude'] >= MIN_LON) & (df_obis['decimalLongitude'] <= MAX_LON)
        ]
        geometry_obis = [Point(xy) for xy in zip(df_obis['decimalLongitude'], df_obis['decimalLatitude'])]
        obis_gdf = gpd.GeoDataFrame(df_obis, geometry=geometry_obis, crs="EPSG:4326")
    else:
        print("Aviso: No se encontraron columnas de lat/lon en OBIS.")
        obis_gdf = gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")
    
    print(f"Registros de Megafauna en BB: {len(obis_gdf)}")

    print("Cargando datos reales de GFW (SAR Vessel Detections)...")
    gfw_dfs = []
    for file in os.listdir(GFW_DIR):
        if file.endswith(".csv"):
            filepath = os.path.join(GFW_DIR, file)
            print(f" Leyendo {filepath}...")
            df_gfw_chunk = pd.read_csv(filepath, low_memory=False)
            # Filtrar Bounding Box GFW
            if 'lat' in df_gfw_chunk.columns and 'lon' in df_gfw_chunk.columns:
                df_gfw_chunk = df_gfw_chunk[
                    (df_gfw_chunk['lat'] >= MIN_LAT) & (df_gfw_chunk['lat'] <= MAX_LAT) &
                    (df_gfw_chunk['lon'] >= MIN_LON) & (df_gfw_chunk['lon'] <= MAX_LON)
                ]
                gfw_dfs.append(df_gfw_chunk)
    
    if gfw_dfs:
        df_gfw = pd.concat(gfw_dfs, ignore_index=True)
        geometry_gfw = [Point(xy) for xy in zip(df_gfw['lon'], df_gfw['lat'])]
        gfw_gdf = gpd.GeoDataFrame(df_gfw, geometry=geometry_gfw, crs="EPSG:4326")
    else:
        df_gfw = pd.DataFrame(columns=['lat', 'lon'])
        gfw_gdf = gpd.GeoDataFrame(columns=['geometry'], crs="EPSG:4326")
    
    print(f"Registros de Buques en BB: {len(gfw_gdf)}")
    
    # Procesar Intersecciones (Spatial Join con H3)
    print("Calculando celdas H3 y unificando Risk Hotsopts...")
    
    if not gfw_gdf.empty:
        gfw_gdf['h3_index'] = gfw_gdf.geometry.apply(lambda p: get_h3_index(p.y, p.x, H3_RESOLUTION))
        vessel_counts = gfw_gdf.groupby('h3_index').size().reset_index(name='vessel_count')
    else:
        vessel_counts = pd.DataFrame(columns=['h3_index', 'vessel_count'])

    if not obis_gdf.empty:
        obis_gdf['h3_index'] = obis_gdf.geometry.apply(lambda p: get_h3_index(p.y, p.x, H3_RESOLUTION))
        megafauna_counts = obis_gdf.groupby('h3_index').size().reset_index(name='megafauna_count')
    else:
        megafauna_counts = pd.DataFrame(columns=['h3_index', 'megafauna_count'])

    merged = pd.merge(vessel_counts, megafauna_counts, on='h3_index', how='outer').fillna(0)
    merged['vessel_count'] = merged['vessel_count'].astype(int)
    merged['megafauna_count'] = merged['megafauna_count'].astype(int)
    
    merged['risk_score'] = merged['vessel_count'] * merged['megafauna_count']
    
    # Exportar resultados
    print("Guardando GeoJSON...")
    if not merged.empty:
        merged['geometry'] = merged['h3_index'].apply(cell_to_polygon)
        gdf_out = gpd.GeoDataFrame(merged, geometry='geometry', crs="EPSG:4326")
    else:
        gdf_out = gpd.GeoDataFrame(columns=['h3_index', 'vessel_count', 'megafauna_count', 'risk_score', 'geometry'], crs="EPSG:4326")

    gdf_out.to_file(OUTPUT_GEOJSON, driver="GeoJSON")
    # Copiar una porcion a data/ para el endpoint vessels
    if not df_gfw.empty:
        df_gfw.to_csv("data/gfw_data.csv", index=False)

    print(f"Prototipo generado exitosamente en {OUTPUT_GEOJSON}")

if __name__ == "__main__":
    run()
