import pandas as pd
import json
import os
import h3
import logging
from typing import List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración
HOTSPOTS_FILE = "data/risk_hotspots.geojson"
VESSELS_FILE = "data/gfw_data.csv"
OBIS_FILE = "data/obis_data.csv"
OUTPUT_CYPHER = "data/knowledge_graph.cypher"
H3_RESOLUTION = 5 # Debe coincidir con spatial_join.py

def generate_cypher():
    """
    Transforma los datos geoespaciales en una serie de comandos Cypher
    para construir el Ocean Knowledge Graph.
    """
    if not all(os.path.exists(f) for f in [HOTSPOTS_FILE, VESSELS_FILE, OBIS_FILE]):
        logger.error("Faltan archivos de datos necesarios para generar el grafo.")
        return

    cypher_commands = []
    
    # 1. Limpieza inicial (Opcional, para desarrollo)
    cypher_commands.append("// --- Reset Graph (Optional) ---")
    cypher_commands.append("// MATCH (n) DETACH DELETE n;")
    
    # 2. Cargar Hotspots
    logger.info("Procesando Hotspots...")
    with open(HOTSPOTS_FILE, 'r') as f:
        hotspots_data = json.load(f)
        for feat in hotspots_data['features']:
            props = feat['properties']
            h3_idx = props['h3_index']
            # Simplificamos coordenadas para el grafo
            coords = feat['geometry']['coordinates'][0][0]
            cmd = (f"MERGE (h:Hotspot {{h3_index: '{h3_idx}'}}) "
                   f"SET h.risk_score = {props['risk_score']}, "
                   f"h.vessel_count = {props['vessel_count']}, "
                   f"h.megafauna_count = {props['megafauna_count']}, "
                   f"h.location = point({{latitude: {coords[1]}, longitude: {coords[0]}}});")
            cypher_commands.append(cmd)

    # 3. Cargar Especies y Avistamientos
    logger.info("Procesando Megafauna y Especies...")
    df_obis = pd.read_csv(OBIS_FILE)
    for idx, row in df_obis.iterrows():
        species = row['species']
        lat, lon = row['decimalLatitude'], row['decimalLongitude']
        h3_idx = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
        occ_id = f"obs_{idx}"
        
        # Merge Especie
        cypher_commands.append(f"MERGE (sp:Species {{name: '{species}'}});")
        
        # Crear Avistamiento y vincular
        cmd = (f"CREATE (s:Sighting {{id: '{occ_id}', date: datetime('{row['eventDate']}')}}) "
               f"SET s.location = point({{latitude: {lat}, longitude: {lon}}});")
        cypher_commands.append(cmd)
        
        cypher_commands.append(f"MATCH (s:Sighting {{id: '{occ_id}'}}), (sp:Species {{name: '{species}'}}) "
                               f"MERGE (s)-[:OF_SPECIES]->(sp);")
        
        cypher_commands.append(f"MATCH (s:Sighting {{id: '{occ_id}'}}), (h:Hotspot {{h3_index: '{h3_idx}'}}) "
                               f"MERGE (s)-[:LOCATED_IN]->(h);")

    # 4. Cargar Buques
    logger.info("Procesando Buques...")
    df_vessels = pd.read_csv(VESSELS_FILE)
    # Agrupamos por MMSI para no crear duplicados de nodos Vessel si aparecen varias veces en el CSV (SAR detections)
    for mmsi, group in df_vessels.groupby('mmsi'):
        v_type = group['vessel_type'].iloc[0]
        cypher_commands.append(f"MERGE (v:Vessel {{mmsi: '{mmsi}', type: '{v_type}'}});")
        
        for _, row in group.iterrows():
            lat, lon = row['lat'], row['lon']
            h3_idx = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
            ts = row['timestamp']
            
            # Vincular Buque con Hotspot mediante una relación con tiempo
            cypher_commands.append(f"MATCH (v:Vessel {{mmsi: '{mmsi}'}}), (h:Hotspot {{h3_index: '{h3_idx}'}}) "
                                   f"MERGE (v)-[:DETECTED_IN {{at: datetime('{ts}')}}]->(h);")

    # Guardar a archivo
    with open(OUTPUT_CYPHER, 'w') as f:
        f.write("\n".join(cypher_commands))
    
    logger.info(f"Éxito: Archivo Cypher generado en {OUTPUT_CYPHER}")
    logger.info(f"Total comandos: {len(cypher_commands)}")

if __name__ == "__main__":
    generate_cypher()
