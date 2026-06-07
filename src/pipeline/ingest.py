"""
ocean_proto / src / pipeline / ingest.py — GFW + OBIS
=====================================================
Pipeline de ingesta que combina Global Fishing Watch (GFW) con el
Sistema de Información sobre Biodiversidad Oceánica (OBIS).

Fuentes integradas:
  1. GFW SAR           — Detecciones satelitales locales (CSV)
  2. GFW Fishing Events — Eventos de pesca AIS (API v3)
  3. O&G Platforms     — BOEM / GFW manual CSV
  4. Support Vessels   — OSVs via GFW vessel search
  5. GAP Events        — Apagones AIS via GFW events
  6. 4Wings Presence   — Heatmap de presencia naval
  7. Encounter Events  — Transbordo en mar (API v3)
  8. Loitering Events  — Merodeo en zona (API v3)
  9. Fishing Effort    — Esfuerzo pesquero 4Wings (proxy biológico)
 10. OBIS Megafauna    — Avistamientos de megafauna marina (API v3)

Esquema unificado ("Unified Ocean DataFrame"):
  timestamp, lat, lon, identity, category, source,
  taxa_group, oil_relevance, vessel_type

La firma de run_ingestion() no cambia para no romper
consumidores existentes (routes.py, spatial_join.py).
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
from src.pipeline.obis_client import fetch_obis_megafauna

logger = logging.getLogger(__name__)

# Bounding box: Baja California Sur / Golfo de California
MIN_LAT, MAX_LAT = 22.0, 32.0
MIN_LON, MAX_LON = -118.0, -105.0

# Directorios de datos locales
GFW_SAR_DIR = "d1f2dc60-3841-11f1-bbe6-bfd704486e22"

# Período de análisis
DATA_START = "2023-01-01"
DATA_END   = "2023-12-31"
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
# FUENTE 10: OBIS — Megafauna marina
# ================================================================
def load_obis_megafauna(
    geometry: str | None = None,
    startdate: str | None = None,
    enddate: str | None = None,
) -> pd.DataFrame:
    """
    Obtiene avistamientos de megafauna marina desde OBIS v3.

    Envuelve ``fetch_obis_megafauna`` y normaliza el resultado al
    esquema unificado del pipeline.  Si la API falla, el cliente OBIS
    ya retorna un DataFrame vacío; esta función lo registra y lo propaga
    de forma silenciosa para no interrumpir el flujo GFW-Only.

    Parameters
    ----------
    geometry  : WKT del polígono de filtro espacial (opcional).
    startdate : Fecha ISO-8601 de inicio (opcional).
    enddate   : Fecha ISO-8601 de fin (opcional).
    """
    df = fetch_obis_megafauna(
        geometry=geometry,
        startdate=startdate,
        enddate=enddate,
    )
    if df.empty:
        logger.info(
            "[OBIS] 0 registros recuperados. "
            "Continuando con flujo GFW-only."
        )
    else:
        logger.info(
            f"[OBIS] {len(df)} avistamientos de megafauna cargados "
            f"({df['species'].nunique()} especies)."
        )
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
# NORMALIZACIÓN — Esquema Unificado ("Unified Ocean DataFrame")
# ================================================================

# Columnas obligatorias del esquema unificado
_UNIFIED_COLS: list[str] = [
    "timestamp",      # str  — fecha/hora del evento o avistamiento
    "lat",            # f64  — latitud decimal WGS-84
    "lon",            # f64  — longitud decimal WGS-84
    "identity",       # str  — MMSI (buques) | nombre de especie (megafauna)
    "category",       # str  — 'vessel' | 'megafauna'
    "source",         # str  — 'gfw' | 'obis'
    # Columnas de metadatos opcionales (NaN donde no aplique)
    "taxa_group",     # str  — Misticeto | Odontoceto | Elasmobranquio | NaN
    "oil_relevance",  # str  — CRÍTICO | ALTO | MEDIO | NaN
    "vessel_type",    # str  — tipo de embarcación GFW | NaN
]


def _normalize_gfw(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza un DataFrame de detecciones GFW al esquema unificado.

    - ``mmsi``       → ``identity``
    - ``timestamp``  → ``timestamp``  (ya existe; se copia)
    - ``lat`` / ``lon`` → numéricos coercitivos
    - ``category``   = 'vessel'
    - ``source``     = 'gfw'
    - Columnas OBIS ausentes rellenadas con ``pd.NA``.
    """
    if df.empty:
        return pd.DataFrame(columns=_UNIFIED_COLS)

    out = pd.DataFrame(index=df.index)
    out["timestamp"]     = df.get("timestamp", pd.NA)
    out["lat"]           = pd.to_numeric(df.get("lat", pd.NA), errors="coerce")
    out["lon"]           = pd.to_numeric(df.get("lon", pd.NA), errors="coerce")
    out["identity"]      = df.get("mmsi", pd.NA).astype(str)
    out["category"]      = "vessel"
    out["source"]        = "gfw"
    out["taxa_group"]    = pd.NA
    out["oil_relevance"] = pd.NA
    out["vessel_type"]   = df.get("vessel_type", pd.NA)
    return out.dropna(subset=["lat", "lon"])


def _normalize_obis(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza un DataFrame de OBIS al esquema unificado.

    - ``species``          → ``identity``
    - ``eventDate``        → ``timestamp``
    - ``decimalLatitude``  → ``lat``
    - ``decimalLongitude`` → ``lon``
    - ``category``         = 'megafauna'
    - ``source``           = 'obis'
    - Columnas GFW ausentes rellenadas con ``pd.NA``.
    """
    if df.empty:
        return pd.DataFrame(columns=_UNIFIED_COLS)

    out = pd.DataFrame(index=df.index)
    out["timestamp"]     = df.get("eventDate", pd.NA)
    out["lat"]           = pd.to_numeric(df.get("decimalLatitude", pd.NA),  errors="coerce")
    out["lon"]           = pd.to_numeric(df.get("decimalLongitude", pd.NA), errors="coerce")
    out["identity"]      = df.get("species", pd.NA).astype(str)
    out["category"]      = "megafauna"
    out["source"]        = "obis"
    out["taxa_group"]    = df.get("taxa_group", pd.NA)
    out["oil_relevance"] = df.get("oil_relevance", pd.NA)
    out["vessel_type"]   = pd.NA
    return out.dropna(subset=["lat", "lon"])


def _normalize_datasets(
    gfw_df: pd.DataFrame,
    obis_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Unifica GFW y OBIS en un único "Unified Ocean DataFrame" con el
    esquema canónico definido en ``_UNIFIED_COLS``.

    Estrategia de concatenación:
    - Normaliza cada fuente de forma independiente (fail-safe).
    - Concatena con ``ignore_index=True``; no duplica columnas.
    - Garantiza tipos numéricos en lat/lon para compatibilidad GeoPandas.
    - Si una fuente está vacía, retorna solo la otra sin warnings críticos.

    Parameters
    ----------
    gfw_df  : DataFrame de detecciones GFW (schema interno del pipeline).
    obis_df : DataFrame de OBIS (schema de ``obis_client.py``).

    Returns
    -------
    pd.DataFrame con columnas ``_UNIFIED_COLS`` y tipos garantizados.
    """
    parts: list[pd.DataFrame] = []

    gfw_norm = _normalize_gfw(gfw_df)
    if not gfw_norm.empty:
        parts.append(gfw_norm)

    obis_norm = _normalize_obis(obis_df)
    if not obis_norm.empty:
        parts.append(obis_norm)

    if not parts:
        logger.warning(
            "[Unified Ocean DF] Ambas fuentes (GFW y OBIS) están vacías."
        )
        return pd.DataFrame(columns=_UNIFIED_COLS)

    unified = pd.concat(parts, ignore_index=True, copy=False)

    # Garantizar tipos: lat/lon siempre float64
    unified["lat"] = unified["lat"].astype("float64")
    unified["lon"] = unified["lon"].astype("float64")

    logger.info(
        f"[Unified Ocean DF] {len(unified)} registros totales — "
        f"GFW: {len(gfw_norm)} | OBIS: {len(obis_norm)} | "
        f"Categorías: {unified['category'].value_counts().to_dict()}"
    )
    return unified


# ================================================================
# PIPELINE PRINCIPAL — GFW + OBIS
# ================================================================

def run_ingestion(
    obis_path: str = None,  # mantenido por compatibilidad de firma — no utilizado
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
    Pipeline de ingesta GFW + OBIS.

    Retorna 6 GeoDataFrames + 2 DataFrames tabulares (firma idéntica
    a la versión GFW-Only para no romper consumidores existentes):
      1. GFW SAR          — Detecciones locales → fallback a CSV
      2. O&G Platforms    — BOEM / GFW manual CSV
      3. Support Vessels  — OSVs via GFW vessel search
      4. GAP Events       — Apagones AIS via GFW events
      5. Encounter Events — Transbordo potencial via GFW events
      6. Loitering Events — Merodeo via GFW events
      7. Fishing Effort   — 4Wings effort report (tabular)
      8. Presence Heatmap — 4Wings presence (tabular)

    Adicionalmente, construye internamente el ``unified_ocean_df``
    (GFW + OBIS normalizados) y lo persiste en ``data/unified_ocean.csv``
    para consumo por los motores de riesgo y análisis geoespacial.
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

    # --- 10. OBIS Megafauna (aditivo, no bloquea el pipeline) ---
    obis_df = load_obis_megafauna(
        geometry=(
            # WKT del bounding box de Baja California Sur / Golfo de California
            f"POLYGON(({MIN_LON} {MIN_LAT},{MAX_LON} {MIN_LAT},"
            f"{MAX_LON} {MAX_LAT},{MIN_LON} {MAX_LAT},{MIN_LON} {MIN_LAT}))"
        ),
        startdate=DATA_START,
        enddate=DATA_END,
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

    # --- Unified Ocean DataFrame (GFW + OBIS normalizados) ---
    unified_df = _normalize_datasets(gfw_df, obis_df)
    if not unified_df.empty:
        os.makedirs("data", exist_ok=True)
        unified_df.to_csv("data/unified_ocean.csv", index=False)
        logger.info(
            f"[Unified Ocean DF] Persistido en data/unified_ocean.csv "
            f"({len(unified_df)} registros)."
        )

    # --- Convertir a GeoDataFrames ---
    def to_gdf_safe(df: pd.DataFrame, lat_col: str, lon_col: str) -> gpd.GeoDataFrame:
        if df.empty:
            return gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:4326")
        df = df.dropna(subset=[lat_col, lon_col]).copy()
        # Coerción defensiva de tipos antes de construir geometrías
        df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
        df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
        df = df.dropna(subset=[lat_col, lon_col])
        # gpd.points_from_xy is vectorized (C-level) — 10x faster than list comprehension
        geom = gpd.points_from_xy(df[lon_col], df[lat_col])
        return gpd.GeoDataFrame(df, geometry=geom, crs="EPSG:4326")

    gfw_gdf        = to_gdf_safe(gfw_df,        "lat", "lon")
    platforms_gdf  = to_gdf_safe(platforms_df,   "lat", "lon")
    support_gdf    = to_gdf_safe(support_df,     "lat", "lon")
    gaps_gdf       = to_gdf_safe(gaps_df,        "lat", "lon")
    encounters_gdf = to_gdf_safe(encounters_df,  "lat", "lon")
    loitering_gdf  = to_gdf_safe(loitering_df,   "lat", "lon")

    logger.info(
        f"Ingesta GFW+OBIS completada — "
        f"SAR: {len(gfw_gdf)} | Platforms: {len(platforms_gdf)} | "
        f"OSVs: {len(support_gdf)} | Gaps: {len(gaps_gdf)} | "
        f"Encounters: {len(encounters_gdf)} | Loitering: {len(loitering_gdf)} | "
        f"Effort: {len(fishing_effort_df)} | Heatmap: {len(heatmap_df)} | "
        f"OBIS Megafauna: {len(obis_df)}"
    )
    return (
        gfw_gdf, platforms_gdf, support_gdf, gaps_gdf,
        encounters_gdf, loitering_gdf, fishing_effort_df, heatmap_df,
    )


if __name__ == "__main__":
    import os as _os
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
    if _os.path.exists("data/unified_ocean.csv"):
        import pandas as _pd
        udf = _pd.read_csv("data/unified_ocean.csv")
        print(f"Unified Ocean  : {len(udf)} registros "
              f"(GFW: {(udf.source=='gfw').sum()} | "
              f"OBIS: {(udf.source=='obis').sum()})")
