"""
ocean_proto / src / pipeline / ingest.py — GFW-ONLY
====================================================
Pipeline de ingesta usando exclusivamente datasets de Global Fishing Watch.

Fuentes integradas:
  1. GFW SAR        — Detecciones satelitales locales (CSV)
  2. GFW Fishing Events — Eventos de pesca AIS (API v3)
  3. O&G Platforms  — BOEM / GFW manual CSV
  4. Support Vessels — OSVs via GFW vessel search
  5. GAP Events     — Apagones AIS via GFW events
  6. 4Wings Presence — Heatmap de presencia naval
  7. Encounter Events — Transbordo en mar (API v3)
  8. Loitering Events — Merodeo en zona (API v3)
  9. Fishing Effort  — Esfuerzo pesquero 4Wings (proxy biológico)

Nota: Esta versión NO usa OBIS ni ERDDAP.
"""

import os
import logging
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

from src.pipeline.gfw_client import (
    fetch_oil_platforms,
    fetch_support_vessels,
    fetch_gap_events,
    fetch_presence_heatmap,
    fetch_encounter_events,
    fetch_loitering_events,
    fetch_fishing_effort_report,
)

logger = logging.getLogger(__name__)

# Bounding box: Baja California Sur / Golfo de California
MIN_LAT, MAX_LAT = 22.0, 32.0
MIN_LON, MAX_LON = -118.0, -105.0

# Directorios de datos locales
GFW_SAR_DIR = "d1f2dc60-3841-11f1-bbe6-bfd704486e22"

# Período de análisis
DATA_START = "2023-01-01"
DATA_END   = "2024-12-31"
BBOX       = (MIN_LON, MIN_LAT, MAX_LON, MAX_LAT)


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
# FUENTES 3-5: Plataformas O&G, Support Vessels, GAP Events
# ================================================================
def load_oil_platforms(bbox: tuple | None = None) -> pd.DataFrame:
    """Carga plataformas offshore de petróleo y gas desde GFW / BOEM."""
    platforms = fetch_oil_platforms(bbox=bbox)
    if not platforms:
        logger.warning("[Oil Platforms] Sin datos de plataformas disponibles.")
        return pd.DataFrame()
    df = pd.DataFrame(platforms)
    if bbox and not df.empty:
        min_lon, min_lat, max_lon, max_lat = bbox
        df = df[
            (df.lat >= min_lat) & (df.lat <= max_lat) &
            (df.lon >= min_lon) & (df.lon <= max_lon)
        ].copy()
    logger.info(f"[Oil Platforms] {len(df)} plataformas O&G en el área de interés.")
    return df


def load_support_vessels(
    bbox: tuple | None = None,
    flags: list[str] | None = None,
) -> pd.DataFrame:
    """Busca buques de apoyo offshore (OSV, PSV, AHTS) via GFW."""
    vessels = fetch_support_vessels(bbox=bbox, flags=flags)
    if not vessels:
        logger.warning("[Support Vessels] Sin buques OSV encontrados.")
        return pd.DataFrame()
    df = pd.DataFrame(vessels)
    logger.info(f"[Support Vessels] {len(df)} buques de apoyo O&G.")
    return df


def load_gap_events(
    bbox:          tuple | None = None,
    start_date:    str   = "2023-01-01",
    end_date:      str   = "2023-12-31",
    min_gap_hours: float = 6.0,
) -> pd.DataFrame:
    """Carga eventos de AIS gap (apagones de transpondedor AIS) via GFW."""
    gaps = fetch_gap_events(
        bbox=bbox, start_date=start_date,
        end_date=end_date, min_gap_hours=min_gap_hours,
    )
    if not gaps:
        logger.warning("[GAP Events] Sin apagones AIS encontrados.")
        return pd.DataFrame()
    df = pd.DataFrame(gaps)
    df.to_csv("data/gfw_gap_events.csv", index=False)
    logger.info(f"[GAP Events] {len(df)} apagones AIS (>= {min_gap_hours}h).")
    return df


# ================================================================
# FUENTES 7-8: Encounter Events, Loitering Events (NUEVAS)
# ================================================================
def load_encounter_events(
    bbox: tuple | None = None,
    start_date: str = "2023-01-01",
    end_date:   str = "2023-12-31",
) -> pd.DataFrame:
    """Carga encuentros entre embarcaciones (transbordo potencial) via GFW."""
    encounters = fetch_encounter_events(
        bbox=bbox, start_date=start_date, end_date=end_date,
    )
    if not encounters:
        logger.warning("[Encounters] Sin eventos de encuentro encontrados.")
        return pd.DataFrame()
    df = pd.DataFrame(encounters)
    logger.info(f"[Encounters] {len(df)} encuentros cargados.")
    return df


def load_loitering_events(
    bbox: tuple | None = None,
    start_date: str = "2023-01-01",
    end_date:   str = "2023-12-31",
) -> pd.DataFrame:
    """Carga eventos de merodeo (loitering) via GFW."""
    loitering = fetch_loitering_events(
        bbox=bbox, start_date=start_date, end_date=end_date,
    )
    if not loitering:
        logger.warning("[Loitering] Sin eventos de merodeo encontrados.")
        return pd.DataFrame()
    df = pd.DataFrame(loitering)
    logger.info(f"[Loitering] {len(df)} eventos de merodeo cargados.")
    return df


# ================================================================
# PIPELINE PRINCIPAL — GFW-ONLY
# ================================================================

def run_ingestion(
    obis_path: str = None,  # ignorado en GFW-only, mantenido por compatibilidad
) -> tuple[
    "gpd.GeoDataFrame",   # gfw_gdf        — detecciones SAR
    "gpd.GeoDataFrame",   # platforms_gdf  — plataformas O&G
    "gpd.GeoDataFrame",   # support_gdf    — buques OSV de apoyo O&G
    "gpd.GeoDataFrame",   # gaps_gdf       — apagones AIS
    "gpd.GeoDataFrame",   # encounters_gdf — encuentros entre buques
    "gpd.GeoDataFrame",   # loitering_gdf  — eventos de merodeo
    "pd.DataFrame",       # fishing_effort — esfuerzo pesquero (CSV)
    "pd.DataFrame",       # heatmap        — presencia naval (CSV)
]:
    """
    Pipeline de ingesta GFW-Only.

    Retorna 6 GeoDataFrames + 2 DataFrames tabulares:
      1. GFW SAR          — Detecciones locales → fallback a CSV
      2. O&G Platforms    — BOEM / GFW manual CSV
      3. Support Vessels  — OSVs via GFW vessel search
      4. GAP Events       — Apagones AIS via GFW events
      5. Encounter Events — Transbordo potencial via GFW events
      6. Loitering Events — Merodeo via GFW events
      7. Fishing Effort   — 4Wings effort report (tabular)
      8. Presence Heatmap — 4Wings presence (tabular)
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

    # --- 2. Plataformas O&G ---
    platforms_df = load_oil_platforms(bbox=BBOX)

    # --- 3. Buques de apoyo O&G (OSVs) ---
    support_df = load_support_vessels(bbox=BBOX)

    # --- 4. GAP Events (apagones AIS) ---
    gaps_df = load_gap_events(
        bbox=BBOX, start_date=DATA_START,
        end_date=DATA_END, min_gap_hours=6.0,
    )

    # --- 5. Encounter Events ---
    encounters_df = load_encounter_events(
        bbox=BBOX, start_date=DATA_START, end_date=DATA_END,
    )

    # --- 6. Loitering Events ---
    loitering_df = load_loitering_events(
        bbox=BBOX, start_date=DATA_START, end_date=DATA_END,
    )

    # --- 7. Fishing Effort (4Wings — tabular, no GDF) ---
    fishing_effort_df = pd.DataFrame()
    try:
        effort = fetch_fishing_effort_report(
            eez_id=8383,
            start_date=DATA_START,
            end_date=min(DATA_END, "2023-12-31"),
            group_by="gearType",
            spatial_resolution="low",
            temporal_resolution="yearly",
        )
        if effort:
            fishing_effort_df = pd.DataFrame(effort)
            fishing_effort_df.to_csv("data/gfw_fishing_effort.csv", index=False)
            logger.info(f"[Fishing Effort] {len(fishing_effort_df)} celdas guardadas.")
    except Exception as e:
        logger.warning(f"[Fishing Effort] Error: {e}")

    # --- 8. Presence Heatmap (4Wings — tabular, no GDF) ---
    heatmap_df = pd.DataFrame()
    try:
        heatmap = fetch_presence_heatmap(
            eez_id=8383,
            start_date=DATA_START,
            end_date=min(DATA_END, "2023-12-31"),
            group_by="gearType",
            spatial_resolution="low",
            temporal_resolution="yearly",
        )
        if heatmap:
            heatmap_df = pd.DataFrame(heatmap)
            heatmap_df.to_csv("data/gfw_heatmap.csv", index=False)
            logger.info(f"[Heatmap] {len(heatmap_df)} celdas guardadas.")
    except Exception as e:
        logger.warning(f"[Heatmap] Error: {e}")

    # --- Convertir a GeoDataFrames ---
    def to_gdf_safe(df, lat_col, lon_col):
        if df.empty:
            return gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:4326")
        df = df.dropna(subset=[lat_col, lon_col]).copy()
        geom = [Point(lon, lat) for lon, lat in zip(df[lon_col], df[lat_col])]
        return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")

    gfw_gdf        = to_gdf_safe(gfw_df,        "lat", "lon")
    platforms_gdf  = to_gdf_safe(platforms_df,   "lat", "lon")
    support_gdf    = to_gdf_safe(support_df,     "lat", "lon")
    gaps_gdf       = to_gdf_safe(gaps_df,        "lat", "lon")
    encounters_gdf = to_gdf_safe(encounters_df,  "lat", "lon")
    loitering_gdf  = to_gdf_safe(loitering_df,   "lat", "lon")

    logger.info(
        f"Ingesta GFW-Only completada — "
        f"SAR: {len(gfw_gdf)} | Platforms: {len(platforms_gdf)} | "
        f"OSVs: {len(support_gdf)} | Gaps: {len(gaps_gdf)} | "
        f"Encounters: {len(encounters_gdf)} | Loitering: {len(loitering_gdf)} | "
        f"Effort: {len(fishing_effort_df)} | Heatmap: {len(heatmap_df)}"
    )
    return (
        gfw_gdf, platforms_gdf, support_gdf, gaps_gdf,
        encounters_gdf, loitering_gdf, fishing_effort_df, heatmap_df,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    (gfw, platforms, support, gaps,
     encounters, loitering, effort, heatmap) = run_ingestion()
    print(f"GFW SAR        : {len(gfw)} detecciones")
    print(f"O&G Platforms  : {len(platforms)} plataformas")
    print(f"OSVs           : {len(support)} buques de apoyo")
    print(f"AIS Gaps       : {len(gaps)} apagones")
    print(f"Encounters     : {len(encounters)} encuentros")
    print(f"Loitering      : {len(loitering)} merodeos")
    print(f"Fishing Effort : {len(effort)} celdas")
    print(f"Heatmap        : {len(heatmap)} celdas")
