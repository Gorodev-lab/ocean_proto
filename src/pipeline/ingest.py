import os
import logging
import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from typing import Tuple

from src.pipeline.gfw_client import (
    fetch_oil_platforms,
    fetch_support_vessels,
    fetch_gap_events,
    fetch_presence_heatmap,
)

logger = logging.getLogger(__name__)

# Bounding box: Baja California Sur / Golfo de California
MIN_LAT, MAX_LAT = 22.0, 32.0
MIN_LON, MAX_LON = -118.0, -105.0

# Directorios de datos locales
GFW_SAR_DIR = "d1f2dc60-3841-11f1-bbe6-bfd704486e22"

# Especies de megafauna original (IDs de WoRMS/OBIS)
OBIS_SPECIES = {
    "Balaenoptera musculus":   137090,  # Ballena azul
    "Megaptera novaeangliae":  137092,  # Ballena jorobada
    "Rhincodon typus":         105847,  # Tiburon ballena
    "Eschrichtius robustus":   137091,  # Ballena gris
    "Manta birostris":         105882,  # Manta
}

# ── Ampliación: Ballenas (Cetacea) afectadas por O&G ─────────────────
# IDs de WoRMS: https://www.marinespecies.org/aphia.php?p=taxdetails&id=...
CETACEAN_SPECIES = {
    # Misticetos (ballenas con barbas) — muy sensibles al ruido sísmico
    "Balaenoptera musculus":   137090,  # Ballena azul   (EN)
    "Balaenoptera physalus":   137013,  # Ballena de aleta (VU)
    "Balaenoptera borealis":   137012,  # Ballena sei (EN)
    "Megaptera novaeangliae":  137092,  # Ballena jorobada (LC)
    "Eschrichtius robustus":   137091,  # Ballena gris (LC)
    "Eubalaena japonica":      254979,  # Ballena franca del Pacífico N (EN)
    # Odontocetos (delfines y cachalotes) — afectados por ruido sonar
    "Physeter macrocephalus":  137119,  # Cachalote (VU)
    "Kogia breviceps":         137124,  # Cachalote pigmeo (LC)
    "Ziphius cavirostris":     343897,  # Bal. pico de ganso (LC)*
    "Mesoplodon densirostris": 343896,  # Bal. de Blainville (LC)*
}
# * particularmente vulnerables a sonares militares y airguns de sísmicos

OBIS_BBOX_WKT = (
    f"POLYGON(({MIN_LON} {MIN_LAT},{MAX_LON} {MIN_LAT},"
    f"{MAX_LON} {MAX_LAT},{MIN_LON} {MAX_LAT},{MIN_LON} {MIN_LAT}))"
)


# ================================================================
# FUENTE 1: GFW — Datos SAR satelitales locales
# ================================================================
def load_gfw_sar_local() -> pd.DataFrame:
    """
    Carga las detecciones SAR de embarcaciones desde los CSV locales de GFW.
    Estos son datos reales de detección por radar de apertura sintética.
    """
    if not os.path.isdir(GFW_SAR_DIR):
        logger.warning(f"Directorio GFW SAR no encontrado: {GFW_SAR_DIR}")
        return pd.DataFrame()

    dfs = []
    for fname in os.listdir(GFW_SAR_DIR):
        if not fname.endswith(".csv"):
            continue
        fpath = os.path.join(GFW_SAR_DIR, fname)
        try:
            df = pd.read_csv(fpath, low_memory=False)
            dfs.append(df)
            logger.info(f"SAR cargado: {fname} ({len(df)} filas)")
        except Exception as e:
            logger.error(f"Error leyendo {fname}: {e}")

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)

    # Filtrar bounding box
    df = df[
        (df.lat >= MIN_LAT) & (df.lat <= MAX_LAT) &
        (df.lon >= MIN_LON) & (df.lon <= MAX_LON)
    ].copy()

    # Normalizar columnas al schema interno
    df = df.rename(columns={"matched_category": "vessel_type"})
    df["mmsi"] = df["mmsi"].fillna("unknown").astype(str)
    df["vessel_type"] = df["vessel_type"].fillna("unknown")

    # Guardar copia para el endpoint /api/vessels
    df[["mmsi", "timestamp", "lat", "lon", "vessel_type"]].to_csv(
        "data/gfw_data.csv", index=False
    )
    logger.info(f"GFW SAR: {len(df)} detecciones reales en BCS")
    return df[["mmsi", "timestamp", "lat", "lon", "vessel_type"]]


# ================================================================
# FUENTE 2: OBIS — API pública de megafauna
# ================================================================
def fetch_obis_megafauna() -> pd.DataFrame:
    """
    Consulta la API pública de OBIS para obtener registros reales de megafauna
    marina dentro del bounding box del Golfo de California / Pacífico BCS.
    Endpoint: https://api.obis.org/v3/occurrence
    """
    all_records = []

    for species_name, taxon_id in OBIS_SPECIES.items():
        url = "https://api.obis.org/v3/occurrence"
        params = {
            "taxonid": taxon_id,
            "geometry": OBIS_BBOX_WKT,
            "size": 500,
        }
        try:
            r = requests.get(url, params=params, timeout=20)
            r.raise_for_status()
            results = r.json().get("results", [])
            for rec in results:
                lat = rec.get("decimalLatitude")
                lon = rec.get("decimalLongitude")
                if lat is not None and lon is not None:
                    all_records.append({
                        "species": species_name,
                        "decimalLatitude": float(lat),
                        "decimalLongitude": float(lon),
                        "eventDate": rec.get("eventDate", ""),
                        "datasetName": rec.get("datasetName", "OBIS"),
                    })
            logger.info(f"OBIS {species_name}: {len(results)} registros")
        except Exception as e:
            logger.error(f"Error OBIS para {species_name}: {e}")

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df.to_csv("data/obis_data.csv", index=False)
    logger.info(f"OBIS total: {len(df)} registros reales de megafauna")
    return df


# ================================================================
# FUENTE 3: OBIS — Ballenas (Cetacea) con IUCN relevantes para O&G
# ================================================================
WHALES_CACHE = "data/obis_whales.csv"

def fetch_obis_whales(use_cache: bool = True) -> pd.DataFrame:
    """
    Consulta la API pública de OBIS para obtener registros de cetáceos
    especialmente afectados por actividades de oil & gas (ruido sísmico,
    derrames, tráfico de buques de apoyo).

    Cachea el resultado en data/obis_whales.csv para evitar re-descargas.
    """
    if use_cache and os.path.exists(WHALES_CACHE):
        df = pd.read_csv(WHALES_CACHE)
        if not df.empty:
            logger.info(
                f"[OBIS Whales] Cargado desde caché: {len(df)} registros"
            )
            return df

    all_records = []
    for species_name, taxon_id in CETACEAN_SPECIES.items():
        url = "https://api.obis.org/v3/occurrence"
        params = {
            "taxonid": taxon_id,
            "geometry": OBIS_BBOX_WKT,
            "size": 1000,   # más registros para análisis de densidad
        }
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            results = r.json().get("results", [])
            for rec in results:
                lat = rec.get("decimalLatitude")
                lon = rec.get("decimalLongitude")
                if lat is None or lon is None:
                    continue
                all_records.append({
                    "species":          species_name,
                    "decimalLatitude":  float(lat),
                    "decimalLongitude": float(lon),
                    "eventDate":        rec.get("eventDate", ""),
                    "datasetName":      rec.get("datasetName", "OBIS"),
                    "taxa_group":       "Cetacea",
                    "oil_relevant":     True,    # marcador para filtros
                })
            logger.info(
                f"[OBIS Whales] {species_name}: {len(results)} registros"
            )
        except Exception as e:
            logger.error(f"[OBIS Whales] Error para {species_name}: {e}")

    if not all_records:
        logger.warning("[OBIS Whales] Sin registros — revisa conectividad o bbox")
        return pd.DataFrame()

    df = pd.DataFrame(all_records)
    df.to_csv(WHALES_CACHE, index=False)
    logger.info(f"[OBIS Whales] Total: {len(df)} registros cetáceos guardados.")
    return df


# ================================================================
# FUENTE 4: GFW Infrastructure — Plataformas O&G (vía gfw_client)
# ================================================================
def load_oil_platforms(bbox: tuple | None = None) -> pd.DataFrame:
    """
    Carga plataformas offshore de petróleo y gas desde GFW Infrastructure API.
    Retorna un DataFrame con columnas [platform_id, lat, lon, category, label, ...].
    """
    platforms = fetch_oil_platforms(bbox=bbox)

    if not platforms:
        logger.warning("[Oil Platforms] Sin datos de plataformas disponibles.")
        return pd.DataFrame()

    df = pd.DataFrame(platforms)

    # Filtrar por bounding box si se especificó
    if bbox and not df.empty:
        min_lon, min_lat, max_lon, max_lat = bbox
        df = df[
            (df.lat  >= min_lat) & (df.lat  <= max_lat) &
            (df.lon  >= min_lon) & (df.lon  <= max_lon)
        ].copy()

    logger.info(f"[Oil Platforms] {len(df)} plataformas O&G en el área de interés.")
    return df


# ================================================================
# FUENTE 5: GFW — Buques de apoyo O&G (OSVs)
# ================================================================
def load_support_vessels(
    bbox: tuple | None = None,
    flags: list[str] | None = None,
) -> pd.DataFrame:
    """
    Busca buques de apoyo offshore (OSV, PSV, AHTS, etc.) via GFW.
    Retorna DataFrame con columnas [vessel_id, mmsi, imo, shipname, flag,
    vessel_type, gear_type, lat, lon, length_m, tonnage_gt, source].
    """
    vessels = fetch_support_vessels(bbox=bbox, flags=flags)
    if not vessels:
        logger.warning("[Support Vessels] Sin buques OSV encontrados.")
        return pd.DataFrame()
    df = pd.DataFrame(vessels)
    logger.info(f"[Support Vessels] {len(df)} buques de apoyo O&G.")
    return df


# ================================================================
# FUENTE 6: GFW — AIS Gap Events (apagones de transpondedor)
# ================================================================
GAP_EVENTS_CACHE_CSV = "data/gfw_gap_events.csv"

def load_gap_events(
    bbox:          tuple | None = None,
    start_date:    str   = "2023-01-01",
    end_date:      str   = "2023-12-31",
    min_gap_hours: float = 6.0,
) -> pd.DataFrame:
    """
    Carga eventos de AIS gap (apagones de transpondedor AIS) via GFW.
    Retorna DataFrame con columnas [gap_id, vessel_id, mmsi, shipname,
    flag, lat, lon, start, end, gap_hours, source].
    """
    gaps = fetch_gap_events(
        bbox=bbox,
        start_date=start_date,
        end_date=end_date,
        min_gap_hours=min_gap_hours,
    )
    if not gaps:
        logger.warning("[GAP Events] Sin apagones AIS encontrados.")
        return pd.DataFrame()
    df = pd.DataFrame(gaps)

    # Persistir para análisis offline
    df.to_csv(GAP_EVENTS_CACHE_CSV, index=False)
    logger.info(f"[GAP Events] {len(df)} apagones AIS (>= {min_gap_hours}h).")
    return df


# ================================================================
# PIPELINE PRINCIPAL
# ================================================================
BBOX = (MIN_LON, MIN_LAT, MAX_LON, MAX_LAT)
# Período de análisis por defecto (últimos 2 años completos)
DATA_START = "2023-01-01"
DATA_END   = "2024-12-31"

def run_ingestion(
    obis_path: str = "data/obis_data.csv",
) -> tuple[
    "gpd.GeoDataFrame",   # gfw_gdf        — detecciones SAR
    "gpd.GeoDataFrame",   # obis_gdf       — megafauna + cetáceos OBIS
    "gpd.GeoDataFrame",   # platforms_gdf  — plataformas O&G
    "gpd.GeoDataFrame",   # support_gdf    — buques OSV de apoyo O&G
    "gpd.GeoDataFrame",   # gaps_gdf       — apagones AIS
]:
    """
    Ejecuta el pipeline completo de ingesta:
      1. GFW SAR        — Detecciones locales → fallback a CSV mock
      2. OBIS           — Megafauna + Cetacea → fallback a CSV local
      3. O&G Platforms  — BOEM / GFW manual CSV
      4. Support Vessels— OSVs via GFW vessel search
      5. GAP Events     — Apagones AIS via GFW events
      6. Heatmap        — 4Wings presence (guarda CSV, no retorna GDF)

    Retorna
    -------
    (gfw_gdf, obis_gdf, platforms_gdf, support_gdf, gaps_gdf)
    """
    # --- 1. GFW SAR ---
    gfw_df = load_gfw_sar_local()
    if gfw_df.empty:
        logger.warning("SAR vacío — usando CSV de fallback para GFW")
        gfw_df = (
            pd.read_csv("data/gfw_data.csv")
            if os.path.exists("data/gfw_data.csv")
            else pd.DataFrame()
        )

    # --- 2. OBIS: megafauna básica + cetáceos O&G ---
    obis_df = pd.DataFrame()
    if os.path.exists(obis_path):
        obis_df = pd.read_csv(obis_path)
        logger.info(f"OBIS cargado desde CSV local: {len(obis_df)} registros")
    if obis_df.empty:
        obis_df = fetch_obis_megafauna()

    # Cetacea enriquecido (caché separada)
    whales_df = fetch_obis_whales(use_cache=True)
    if not whales_df.empty:
        # Unir al dataframe principal, evitando duplicados por coordenada+especie
        obis_df = pd.concat([obis_df, whales_df], ignore_index=True)
        obis_df = obis_df.drop_duplicates(
            subset=["species", "decimalLatitude", "decimalLongitude"]
        )
        logger.info(
            f"OBIS consolidado (megafauna + cetáceos): {len(obis_df)} registros"
        )

    # Filtrar bbox en OBIS
    if not obis_df.empty and "decimalLatitude" in obis_df.columns:
        obis_df = obis_df[
            (obis_df.decimalLatitude  >= MIN_LAT) &
            (obis_df.decimalLatitude  <= MAX_LAT) &
            (obis_df.decimalLongitude >= MIN_LON) &
            (obis_df.decimalLongitude <= MAX_LON)
        ].dropna(subset=["decimalLatitude", "decimalLongitude"])

    # --- 3. Plataformas O&G ---
    platforms_df = load_oil_platforms(bbox=BBOX)

    # --- 4. Buques de apoyo O&G (OSVs) ---
    support_df = load_support_vessels(bbox=BBOX)

    # --- 5. GAP Events (apagones AIS) ---
    gaps_df = load_gap_events(
        bbox=BBOX,
        start_date=DATA_START,
        end_date=DATA_END,
        min_gap_hours=6.0,
    )

    # --- 6. Heatmap 4Wings (presencia por hex, solo CSV) ---
    try:
        heatmap = fetch_presence_heatmap(
            eez_id=8383,
            start_date=DATA_START,
            end_date=min(DATA_END, "2023-12-31"),   # máx 366 días
            group_by="gearType",
            spatial_resolution="low",
            temporal_resolution="yearly",
        )
        if heatmap:
            import pandas as _pd
            _pd.DataFrame(heatmap).to_csv("data/gfw_heatmap.csv", index=False)
            logger.info(f"[Heatmap] {len(heatmap)} celdas guardadas en data/gfw_heatmap.csv")
    except Exception as e:
        logger.warning(f"[Heatmap] Error al obtener heatmap 4Wings: {e}")

    # --- Convertir a GeoDataFrames ---
    def to_gdf_safe(df, lat_col, lon_col):
        if df.empty:
            return gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:4326")
        df = df.dropna(subset=[lat_col, lon_col]).copy()
        geom = [Point(lon, lat) for lon, lat in zip(df[lon_col], df[lat_col])]
        return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")

    gfw_gdf       = to_gdf_safe(gfw_df,       "lat",              "lon")
    obis_gdf      = to_gdf_safe(obis_df,      "decimalLatitude",  "decimalLongitude")
    platforms_gdf = to_gdf_safe(platforms_df, "lat",              "lon")
    support_gdf   = to_gdf_safe(support_df,   "lat",              "lon")
    gaps_gdf      = to_gdf_safe(gaps_df,      "lat",              "lon")

    logger.info(
        f"Ingesta completada — "
        f"GFW SAR: {len(gfw_gdf)} | "
        f"OBIS: {len(obis_gdf)} | "
        f"Platforms: {len(platforms_gdf)} | "
        f"OSVs: {len(support_gdf)} | "
        f"Gaps AIS: {len(gaps_gdf)}"
    )
    return gfw_gdf, obis_gdf, platforms_gdf, support_gdf, gaps_gdf


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    gfw, obis, platforms, support, gaps = run_ingestion()
    print(f"GFW SAR        : {len(gfw)} detecciones")
    print(f"OBIS megafauna : {len(obis)} registros")
    print(f"O&G Platforms  : {len(platforms)} plataformas")
    print(f"OSVs           : {len(support)} buques de apoyo")
    print(f"AIS Gaps       : {len(gaps)} apagones")
