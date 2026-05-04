"""
ocean_proto / src / pipeline / oceanographic.py
===============================================
Criterios oceanográficos abióticos para el pipeline de riesgo.

Módulos:
  - fetch_sst_erddap()       : Temperatura superficial del mar (NOAA OISST v2.1)
  - fetch_chlorophyll_erddap(): Clorofila-a (MODIS Aqua, NASA OceanColor vía ERDDAP)
  - compute_upwelling_index() : Índice de upwelling (proxy de gradiente SST)
  - OceanographicGrid        : Contenedor unificado con interpolación a celdas H3

Fuentes de datos:
  ERDDAP (NOAA CoastWatch): https://coastwatch.pfeg.noaa.gov/erddap
    - ncdcOisst21Agg_LonPM180  →  SST diaria 0.25° (OISST v2.1)
    - erdMH1chla8day            →  Chl-a 8-day 4 km (MODIS Aqua)

Todos los endpoints son públicos y gratuitos — sin token requerido.
"""

import os
import logging
import time
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional

import requests
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ── Configuración ─────────────────────────────────────────────────────────────
ERDDAP_BASE = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"

# Bounding box del proyecto (hereda de ingest.py)
MIN_LAT, MAX_LAT = 22.0, 32.0
MIN_LON, MAX_LON = -118.0, -105.0

# Directorios de caché
OCEAN_CACHE_DIR = "data/oceanographic"
SST_CACHE       = os.path.join(OCEAN_CACHE_DIR, "sst_cache.json")
CHL_CACHE       = os.path.join(OCEAN_CACHE_DIR, "chl_cache.json")
BATHY_CACHE     = os.path.join(OCEAN_CACHE_DIR, "bathy_cache.json")

SST_CACHE_EXPIRY = 86400    # 24 horas — SST cambia diariamente
CHL_CACHE_EXPIRY = 691200   # 8 días  — Chl-a es compuesto 8-day
ERDDAP_TIMEOUT   = 60       # segundos

os.makedirs(OCEAN_CACHE_DIR, exist_ok=True)


# ── Utilidades de caché ───────────────────────────────────────────────────────

def _load_cache(path: str, expiry_seconds: int) -> Optional[list]:
    """Carga caché JSON si existe y no ha expirado."""
    if not os.path.exists(path):
        return None
    age = time.time() - os.path.getmtime(path)
    if age > expiry_seconds:
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _save_cache(path: str, data: list) -> None:
    """Persiste datos en caché JSON."""
    try:
        with open(path, "w") as f:
            json.dump(data, f, default=str)
    except IOError as e:
        logger.warning(f"No se pudo guardar caché en {path}: {e}")


# ── FUENTE 1: SST — NOAA OISST v2.1 vía ERDDAP ───────────────────────────────

def fetch_sst_erddap(
    start_date: str = "2024-01-01",
    end_date:   str = "2024-12-31",
    bbox: tuple = (MIN_LON, MIN_LAT, MAX_LON, MAX_LAT),
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Descarga SST mensual promedio desde NOAA OISST v2.1 via ERDDAP.

    ERDDAP Dataset: ncdcOisst21Agg_LonPM180
    Variables: sst (°C), anom (anomalía térmica vs climatología 1971-2000)

    Estrategia de optimización:
      - Solicita promedio mensual en lugar de diario para reducir tamaño
      - Resolución OISST: 0.25° → suficiente para celdas H3 resolución 5-7
      - Caché local de 24h para evitar re-descargas frecuentes

    Parámetros
    ----------
    start_date : ISO date, inicio del período de análisis
    end_date   : ISO date, fin del período de análisis
    bbox       : (min_lon, min_lat, max_lon, max_lat)
    use_cache  : Si True, usa caché si está vigente

    Retorna
    -------
    DataFrame: [time, latitude, longitude, sst, sst_anomaly]
    """
    if use_cache:
        cached = _load_cache(SST_CACHE, SST_CACHE_EXPIRY)
        if cached is not None:
            df = pd.DataFrame(cached)
            logger.info(f"[SST] Caché vigente: {len(df)} registros.")
            return df

    min_lon, min_lat, max_lon, max_lat = bbox

    # ERDDAP URL para SST + anomalía, subsampling cada 1° para reducir payload
    # Formato: variable[(tiempo):(tiempo)][(lat_min):(lat_stride):(lat_max)][(lon_min):(lon_stride):(lon_max)]
    # stride 4 → toma 1 de cada 4 píxeles (0.25° × 4 = ~1° efectivo)
    dataset_id = "ncdcOisst21Agg_LonPM180"
    url = (
        f"{ERDDAP_BASE}/{dataset_id}.csv"
        f"?sst,anom"
        f"[({start_date}T00:00:00Z):1:({end_date}T00:00:00Z)]"
        f"[0:1:0]"                        # zlev: solo superficie
        f"[({min_lat:.2f}):4:({max_lat:.2f})]"   # lat con stride 4
        f"[({min_lon:.2f}):4:({max_lon:.2f})]"   # lon con stride 4
    )

    logger.info(f"[SST ERDDAP] Descargando SST ({start_date} → {end_date})...")
    logger.debug(f"  URL: {url}")

    try:
        r = requests.get(url, timeout=ERDDAP_TIMEOUT)
        r.raise_for_status()

        # ERDDAP retorna CSV con 2 filas de header (names + units), skip ambas
        from io import StringIO
        df = pd.read_csv(StringIO(r.text), skiprows=[1])  # skip unidades
        df.columns = df.columns.str.strip()

        # Renombrar a schema interno
        rename_map = {
            "time":      "time",
            "latitude":  "latitude",
            "longitude": "longitude",
            "sst":       "sst",
            "anom":      "sst_anomaly",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        # Limpiar NaN (valores oceánicos inválidos o tierra)
        df = df.dropna(subset=["sst"]).copy()
        df["sst"]         = pd.to_numeric(df["sst"], errors="coerce")
        df["sst_anomaly"] = pd.to_numeric(df.get("sst_anomaly", pd.Series()), errors="coerce")

        logger.info(f"[SST ERDDAP] {len(df)} puntos de SST descargados.")
        _save_cache(SST_CACHE, df.to_dict(orient="records"))
        return df

    except requests.exceptions.Timeout:
        logger.error("[SST ERDDAP] Timeout — ERDDAP tardó demasiado. Prueba un rango de fechas más corto.")
    except requests.exceptions.HTTPError as e:
        logger.error(f"[SST ERDDAP] HTTP {e.response.status_code}: {e.response.text[:300]}")
    except Exception as e:
        logger.error(f"[SST ERDDAP] Error inesperado: {e}")

    return pd.DataFrame(columns=["time", "latitude", "longitude", "sst", "sst_anomaly"])


# ── FUENTE 2: Clorofila-a — MODIS Aqua via ERDDAP ────────────────────────────

def fetch_chlorophyll_erddap(
    start_date: str = "2024-01-01",
    end_date:   str = "2024-12-31",
    bbox: tuple = (MIN_LON, MIN_LAT, MAX_LON, MAX_LAT),
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Descarga Clorofila-a 8-day composite desde MODIS Aqua via ERDDAP.

    ERDDAP Dataset: erdMH1chla8day
    Variable: chlorophyll (mg/m³)
    Resolución: ~4 km (0.041667°)

    Parámetros
    ----------
    start_date : ISO date
    end_date   : ISO date
    bbox       : (min_lon, min_lat, max_lon, max_lat)
    use_cache  : Si True, usa caché si está vigente

    Retorna
    -------
    DataFrame: [time, latitude, longitude, chlorophyll_mg_m3]
    """
    if use_cache:
        cached = _load_cache(CHL_CACHE, CHL_CACHE_EXPIRY)
        if cached is not None:
            df = pd.DataFrame(cached)
            logger.info(f"[Chl-a] Caché vigente: {len(df)} registros.")
            return df

    min_lon, min_lat, max_lon, max_lat = bbox

    # Stride 24 → ~1° efectivo para reducir payload (4km × 24 ≈ 96km ~ 1°)
    dataset_id = "erdMH1chla8day"
    url = (
        f"{ERDDAP_BASE}/{dataset_id}.csv"
        f"?chlorophyll"
        f"[({start_date}T00:00:00Z):1:({end_date}T00:00:00Z)]"
        f"[({min_lat:.4f}):24:({max_lat:.4f})]"
        f"[({min_lon:.4f}):24:({max_lon:.4f})]"
    )

    logger.info(f"[Chl-a ERDDAP] Descargando Clorofila-a ({start_date} → {end_date})...")
    logger.debug(f"  URL: {url}")

    try:
        r = requests.get(url, timeout=ERDDAP_TIMEOUT)
        r.raise_for_status()

        from io import StringIO
        df = pd.read_csv(StringIO(r.text), skiprows=[1])
        df.columns = df.columns.str.strip()

        rename_map = {
            "time":         "time",
            "latitude":     "latitude",
            "longitude":    "longitude",
            "chlorophyll":  "chlorophyll_mg_m3",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        # Clorofila: valores negativos o > 100 son inválidos (nubes, tierra)
        if "chlorophyll_mg_m3" in df.columns:
            df["chlorophyll_mg_m3"] = pd.to_numeric(df["chlorophyll_mg_m3"], errors="coerce")
            df = df[(df["chlorophyll_mg_m3"] > 0) & (df["chlorophyll_mg_m3"] < 100)].copy()

        logger.info(f"[Chl-a ERDDAP] {len(df)} puntos de Chl-a descargados.")
        _save_cache(CHL_CACHE, df.to_dict(orient="records"))
        return df

    except requests.exceptions.Timeout:
        logger.error("[Chl-a ERDDAP] Timeout — prueba un rango más corto o usa caché.")
    except requests.exceptions.HTTPError as e:
        logger.error(f"[Chl-a ERDDAP] HTTP {e.response.status_code}: {e.response.text[:300]}")
    except Exception as e:
        logger.error(f"[Chl-a ERDDAP] Error inesperado: {e}")

    return pd.DataFrame(columns=["time", "latitude", "longitude", "chlorophyll_mg_m3"])


# ── ANÁLISIS: Estadísticas espaciales por grilla regular ─────────────────────

def aggregate_to_grid(
    df: pd.DataFrame,
    value_col: str,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    resolution_deg: float = 1.0,
) -> pd.DataFrame:
    """
    Agrega datos puntuales a una grilla regular (media, std, percentiles).
    Útil para interpolar SST/Chl-a a celdas H3.

    Retorna DataFrame: [grid_lat, grid_lon, mean, std, p25, p75, count]
    """
    if df.empty or value_col not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df["grid_lat"] = (df[lat_col] // resolution_deg) * resolution_deg + resolution_deg / 2
    df["grid_lon"] = (df[lon_col] // resolution_deg) * resolution_deg + resolution_deg / 2

    grouped = df.groupby(["grid_lat", "grid_lon"])[value_col].agg(
        mean="mean",
        std="std",
        p25=lambda x: x.quantile(0.25),
        p75=lambda x: x.quantile(0.75),
        count="count",
    ).reset_index()

    return grouped


def compute_upwelling_index(sst_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula un índice simplificado de upwelling basado en el gradiente
    latitudinal de SST (costa más fría = upwelling activo).

    El upwelling del Pacífico BCS ocurre principalmente en la costa
    occidental (LON ≈ -117 a -113°), con agua más fría cerca de la costa.

    Parámetros
    ----------
    sst_df : DataFrame con columnas [latitude, longitude, sst]

    Retorna
    -------
    DataFrame: [grid_lat, grid_lon, sst_mean, upwelling_index]
      upwelling_index: 0-1 (1 = upwelling intenso, 0 = sin upwelling)
    """
    if sst_df.empty:
        return pd.DataFrame()

    grid = aggregate_to_grid(sst_df, "sst", resolution_deg=1.0)
    if grid.empty:
        return pd.DataFrame()

    # Normalizar SST invertida (SST más baja = upwelling más fuerte)
    sst_min = grid["mean"].min()
    sst_max = grid["mean"].max()
    sst_range = sst_max - sst_min

    if sst_range > 0:
        grid["upwelling_index"] = (sst_max - grid["mean"]) / sst_range
    else:
        grid["upwelling_index"] = 0.0

    grid.rename(columns={"mean": "sst_mean"}, inplace=True)
    logger.info(f"[Upwelling] Índice calculado para {len(grid)} celdas.")
    return grid


# ── FUENTE 3: Batimetría — ETOPO2022 vía ERDDAP ───────────────────────────────

def fetch_bathymetry_erddap(
    bbox: tuple = (MIN_LON, MIN_LAT, MAX_LON, MAX_LAT),
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Descarga batimetría ETOPO2022 (1 arc-minute) desde ERDDAP.

    ERDDAP Dataset: ETOPO_2022_v1_60s_N90W180_bed
    Variable: z (elevación en metros; negativo = profundidad)

    Notas:
      - Datos estáticos (no cambian): caché es permanente hasta borrarla
      - Stride 10 → resolución efectiva ~10 arc-min (~18 km) suficiente para H3-5

    Parámetros
    ----------
    bbox : (min_lon, min_lat, max_lon, max_lat)

    Retorna
    -------
    DataFrame: [latitude, longitude, depth_m]
      depth_m: positivo = profundidad bajo el nivel del mar
    """
    if use_cache and os.path.exists(BATHY_CACHE):
        # Batimetría es estática — caché indefinida
        try:
            with open(BATHY_CACHE) as f:
                cached = json.load(f)
            df = pd.DataFrame(cached)
            logger.info(f"[Batimetría] Caché local: {len(df)} puntos.")
            return df
        except (json.JSONDecodeError, IOError):
            pass

    min_lon, min_lat, max_lon, max_lat = bbox

    # ETOPO2022 en ERDDAP (NOAA NCEI)
    etopo_base = "https://www.ncei.noaa.gov/erddap/griddap"
    dataset_id = "ETOPO_2022_v1_60s_N90W180_bed"
    url = (
        f"{etopo_base}/{dataset_id}.csv"
        f"?z"
        f"[({min_lat:.4f}):10:({max_lat:.4f})]"
        f"[({min_lon:.4f}):10:({max_lon:.4f})]"
    )

    logger.info(f"[Batimetría ERDDAP] Descargando ETOPO2022 para el bbox...")
    logger.debug(f"  URL: {url}")

    try:
        r = requests.get(url, timeout=120)  # batimetría puede tardar más
        r.raise_for_status()

        from io import StringIO
        df = pd.read_csv(StringIO(r.text), skiprows=[1])
        df.columns = df.columns.str.strip()

        rename_map = {
            "latitude":  "latitude",
            "longitude": "longitude",
            "z":         "elevation_m",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        # Convertir elevación a profundidad (positivo = bajo el mar)
        df["depth_m"] = -df["elevation_m"].clip(upper=0)  # solo parte submarina
        df["elevation_m"] = pd.to_numeric(df["elevation_m"], errors="coerce")
        df["depth_m"]     = pd.to_numeric(df["depth_m"], errors="coerce")

        logger.info(f"[Batimetría] {len(df)} puntos descargados de ETOPO2022.")
        _save_cache(BATHY_CACHE, df.to_dict(orient="records"))
        return df

    except requests.exceptions.Timeout:
        logger.error("[Batimetría ERDDAP] Timeout — la descarga de batimetría puede tardar hasta 2 min.")
    except requests.exceptions.HTTPError as e:
        logger.error(f"[Batimetría ERDDAP] HTTP {e.response.status_code}: {e.response.text[:300]}")
    except Exception as e:
        logger.error(f"[Batimetría ERDDAP] Error inesperado: {e}")

    return pd.DataFrame(columns=["latitude", "longitude", "elevation_m", "depth_m"])


def classify_geomorphology(depth_m: float) -> str:
    """
    Clasifica el ambiente batimétrico en categorías estándar.

    Retorna una de: 'estuary', 'shelf', 'slope', 'abyss', 'hadal'
    """
    if depth_m < 0:
        return "land"
    elif depth_m < 50:
        return "estuary"
    elif depth_m < 200:
        return "shelf"
    elif depth_m < 2000:
        return "slope"
    elif depth_m < 6000:
        return "abyss"
    else:
        return "hadal"
