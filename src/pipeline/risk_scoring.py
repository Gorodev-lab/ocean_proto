"""
ocean_proto / src / pipeline / risk_scoring.py
=============================================
Motor de composite risk scoring multidimensional.

Integra todos los criterios oceanográficos + bióticos + antrópicos
en un único Composite Risk Score (CRS) por celda H3.

Score actual (baseline):
  risk_score = vessel_count × megafauna_count  [proxy simple]

Nuevo Composite Risk Score:
  CRS = Σ(w_i × normalized_score_i) × temporal_modifier

Criterios y pesos:
  w_co_occurrence  = 0.25  →  vessel × megafauna (base)
  w_acoustic       = 0.20  →  SPL acumulado en celda
  w_sst            = 0.15  →  Proximidad al rango óptimo de SST
  w_productivity   = 0.15  →  Clorofila-a (intensidad de upwelling)
  w_gap_events     = 0.10  →  Densidad de apagones AIS
  w_bathymetry     = 0.10  →  Overlap hábitat-profundidad
  w_current        = 0.05  →  Índice de upwelling

Todos los scores parciales se normalizan a [0, 1] antes de ponderar.
El temporal_modifier amplifica el CRS según la estacionalidad de las
especies presentes en la celda.
"""

import logging
import math
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ── Pesos del composite score ─────────────────────────────────────────────────
WEIGHTS: Dict[str, float] = {
    "co_occurrence": 0.25,
    "acoustic":      0.20,
    "sst":           0.15,
    "productivity":  0.15,
    "gap_events":    0.10,
    "bathymetry":    0.10,
    "upwelling":     0.05,
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Los pesos deben sumar 1.0"

# ── Rangos óptimos de SST por especie (°C) ────────────────────────────────────
# Fuente: literatura de biología marina del Golfo de California
SST_OPTIMAL_RANGES: Dict[str, tuple] = {
    "Balaenoptera musculus":   (16.0, 24.0),
    "Balaenoptera physalus":   (14.0, 22.0),
    "Balaenoptera borealis":   (10.0, 20.0),
    "Megaptera novaeangliae":  (18.0, 26.0),
    "Eschrichtius robustus":   (10.0, 20.0),
    "Eubalaena japonica":      (8.0,  18.0),
    "Physeter macrocephalus":  (15.0, 30.0),
    "Kogia breviceps":         (15.0, 28.0),
    "Ziphius cavirostris":     (14.0, 28.0),
    "Mesoplodon densirostris": (15.0, 28.0),
    "Rhincodon typus":         (22.0, 30.0),
    "Manta birostris":         (20.0, 30.0),
}

# Rango batimétrico preferido por especie (metros de profundidad)
DEPTH_PREFERRED_RANGES: Dict[str, tuple] = {
    "Balaenoptera musculus":   (50,  3000),   # alimentación en pared continental
    "Balaenoptera physalus":   (100, 2000),
    "Balaenoptera borealis":   (100, 2000),
    "Megaptera novaeangliae":  (0,   2000),   # costera y pelágica
    "Eschrichtius robustus":   (0,   100),    # lagunas y aguas someras
    "Eubalaena japonica":      (0,   500),
    "Physeter macrocephalus":  (200, 6000),   # buceador profundo
    "Kogia breviceps":         (200, 4000),
    "Ziphius cavirostris":     (500, 5000),   # cañones profundos
    "Mesoplodon densirostris": (200, 3000),
    "Rhincodon typus":         (0,   700),    # epipelágico
    "Manta birostris":         (0,   500),    # superficie y epipelágico
}


# ── Funciones de normalización ────────────────────────────────────────────────

def _normalize_minmax(value: float, min_val: float, max_val: float) -> float:
    """Normaliza un valor al rango [0, 1] usando min-max scaling."""
    if max_val == min_val:
        return 0.0
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))


def _sst_proximity_score(sst: float, species_list: List[str]) -> float:
    """
    Calcula cuánto se superpone la SST actual con el rango óptimo
    de las especies presentes en la celda.

    Retorna: [0, 1] — 1 = todas las especies en rango óptimo
    """
    if not species_list or math.isnan(sst):
        return 0.0

    scores = []
    for sp in species_list:
        opt_range = SST_OPTIMAL_RANGES.get(sp)
        if not opt_range:
            scores.append(0.5)  # neutral si desconocido
            continue
        lo, hi = opt_range
        if lo <= sst <= hi:
            # Dentro del rango: score = 1 (bonus si está cerca del centro)
            center = (lo + hi) / 2
            distance_from_center = abs(sst - center) / ((hi - lo) / 2)
            scores.append(1.0 - 0.3 * distance_from_center)
        else:
            # Fuera del rango: decae linealmente con la distancia
            deviation = min(abs(sst - lo), abs(sst - hi))
            score = max(0.0, 1.0 - deviation / 5.0)   # decae a 0 en 5°C fuera
            scores.append(score)

    return float(np.mean(scores)) if scores else 0.0


def _depth_habitat_score(depth_m: float, species_list: List[str]) -> float:
    """
    Calcula cuánto se superpone la batimetría de la celda con el
    rango preferido de profundidad de las especies presentes.

    Retorna: [0, 1]
    """
    if not species_list or math.isnan(depth_m):
        return 0.5  # valor neutral si no hay datos

    scores = []
    for sp in species_list:
        depth_range = DEPTH_PREFERRED_RANGES.get(sp)
        if not depth_range:
            scores.append(0.5)
            continue
        lo, hi = depth_range
        if lo <= depth_m <= hi:
            scores.append(1.0)
        else:
            deviation = min(abs(depth_m - lo), abs(depth_m - hi))
            score = max(0.0, 1.0 - deviation / 500.0)
            scores.append(score)

    return float(np.mean(scores)) if scores else 0.5


# ── Motor principal ───────────────────────────────────────────────────────────

def compute_composite_risk_score(
    hotspots_df:   pd.DataFrame,
    acoustic_df:   pd.DataFrame          = None,
    sst_grid:      pd.DataFrame          = None,
    chl_grid:      pd.DataFrame          = None,
    bathy_grid:    pd.DataFrame          = None,
    upwelling_df:  pd.DataFrame          = None,
    gaps_hex_df:   pd.DataFrame          = None,
    species_per_hex: Dict[str, List[str]] = None,
    analysis_month: Optional[int]         = None,
) -> pd.DataFrame:
    """
    Calcula el Composite Risk Score para cada celda H3.

    Parámetros
    ----------
    hotspots_df     : DataFrame base [h3_index, vessel_count, megafauna_count, risk_score]
    acoustic_df     : DataFrame [h3_index, estimated_spl_db, acoustic_risk_score]
    sst_grid        : DataFrame [grid_lat, grid_lon, sst_mean]
    chl_grid        : DataFrame [grid_lat, grid_lon, chlorophyll_mg_m3]
    bathy_grid      : DataFrame [grid_lat, grid_lon, depth_m]  (si disponible)
    upwelling_df    : DataFrame [grid_lat, grid_lon, upwelling_index]
    gaps_hex_df     : DataFrame [h3_index, gap_count]
    species_per_hex : dict {h3_index: [list de especies observadas]}
    analysis_month  : mes para el modificador temporal (1-12)

    Retorna
    -------
    DataFrame: [h3_index, crs, crs_level, ...sub-scores...]
    """
    if hotspots_df.empty:
        logger.warning("[CRS] hotspots_df vacío — sin composite score.")
        return pd.DataFrame()

    df = hotspots_df.copy()
    df["h3_index"] = df["h3_index"].astype(str)

    # ── 1. Score de Co-ocurrencia (normalizado) ────────────────────────────
    max_cooc = df["risk_score"].max()
    df["score_co_occurrence"] = df["risk_score"].apply(
        lambda x: _normalize_minmax(x, 0, max_cooc) if max_cooc > 0 else 0.0
    )

    # ── 2. Score Acústico ──────────────────────────────────────────────────
    if acoustic_df is not None and not acoustic_df.empty:
        acoustic_map = acoustic_df.set_index("h3_index")["acoustic_risk_score"].to_dict()
        max_acoustic = max(acoustic_map.values()) if acoustic_map else 4
        df["score_acoustic"] = df["h3_index"].map(
            lambda h: _normalize_minmax(acoustic_map.get(h, 0), 0, max_acoustic)
        )
        df["estimated_spl_db"] = df["h3_index"].map(
            lambda h: acoustic_df.set_index("h3_index")["estimated_spl_db"].to_dict().get(h, 0)
        )
    else:
        df["score_acoustic"]   = 0.0
        df["estimated_spl_db"] = 0.0

    # ── 3. Score SST ───────────────────────────────────────────────────────
    # Aproximación: asignar SST al centroide de la celda H3
    df["score_sst"] = 0.5  # valor neutral por defecto
    df["sst_mean"]  = float("nan")

    if sst_grid is not None and not sst_grid.empty and species_per_hex:
        try:
            import h3 as h3lib
            for idx, row in df.iterrows():
                hex_id = row["h3_index"]
                lat, lon = h3lib.cell_to_latlng(hex_id)
                # Buscar celda de grilla SST más cercana
                lat_col = "grid_lat" if "grid_lat" in sst_grid.columns else "latitude"
                lon_col = "grid_lon" if "grid_lon" in sst_grid.columns else "longitude"
                sst_col = "sst_mean" if "sst_mean" in sst_grid.columns else "sst"

                dists = np.sqrt(
                    (sst_grid[lat_col] - lat) ** 2 +
                    (sst_grid[lon_col] - lon) ** 2
                )
                nearest_idx = dists.idxmin()
                sst_val = sst_grid.loc[nearest_idx, sst_col]
                df.at[idx, "sst_mean"] = sst_val

                sp_list = species_per_hex.get(hex_id, [])
                df.at[idx, "score_sst"] = _sst_proximity_score(float(sst_val), sp_list)
        except ImportError:
            logger.warning("[CRS] h3 no disponible para cálculo de SST por celda.")
        except Exception as e:
            logger.warning(f"[CRS] Error calculando score SST: {e}")

    # ── 4. Score Productividad (Clorofila-a) ───────────────────────────────
    df["score_productivity"] = 0.0
    df["chlorophyll_mg_m3"]  = float("nan")

    if chl_grid is not None and not chl_grid.empty:
        try:
            import h3 as h3lib
            chl_col = "chlorophyll_mg_m3" if "chlorophyll_mg_m3" in chl_grid.columns else "chlorophyll"
            lat_col = "grid_lat" if "grid_lat" in chl_grid.columns else "latitude"
            lon_col = "grid_lon" if "grid_lon" in chl_grid.columns else "longitude"
            max_chl = chl_grid[chl_col].quantile(0.95)  # usar p95 para normalizar

            for idx, row in df.iterrows():
                hex_id = row["h3_index"]
                lat, lon = h3lib.cell_to_latlng(hex_id)
                dists = np.sqrt(
                    (chl_grid[lat_col] - lat) ** 2 +
                    (chl_grid[lon_col] - lon) ** 2
                )
                nearest_idx = dists.idxmin()
                chl_val = chl_grid.loc[nearest_idx, chl_col]
                df.at[idx, "chlorophyll_mg_m3"] = chl_val
                df.at[idx, "score_productivity"] = _normalize_minmax(float(chl_val), 0, max_chl)
        except Exception as e:
            logger.warning(f"[CRS] Error calculando score Chl-a: {e}")

    # ── 5. Score Gap Events ────────────────────────────────────────────────
    if gaps_hex_df is not None and not gaps_hex_df.empty and "h3_index" in gaps_hex_df.columns:
        gap_map = gaps_hex_df.set_index("h3_index")["gap_count"].to_dict()
        max_gaps = max(gap_map.values()) if gap_map else 1
        df["score_gap_events"] = df["h3_index"].map(
            lambda h: _normalize_minmax(gap_map.get(h, 0), 0, max_gaps)
        )
        df["gap_count"] = df["h3_index"].map(lambda h: gap_map.get(h, 0))
    else:
        df["score_gap_events"] = 0.0
        df["gap_count"]        = 0

    # ── 6. Score Batimetría ────────────────────────────────────────────────
    df["score_bathymetry"] = 0.5
    df["depth_m"]          = float("nan")

    if bathy_grid is not None and not bathy_grid.empty and species_per_hex:
        try:
            import h3 as h3lib
            lat_col   = "grid_lat" if "grid_lat" in bathy_grid.columns else "latitude"
            lon_col   = "grid_lon" if "grid_lon" in bathy_grid.columns else "longitude"
            depth_col = "depth_m"

            if depth_col in bathy_grid.columns:
                for idx, row in df.iterrows():
                    hex_id = row["h3_index"]
                    lat, lon = h3lib.cell_to_latlng(hex_id)
                    dists = np.sqrt(
                        (bathy_grid[lat_col] - lat) ** 2 +
                        (bathy_grid[lon_col] - lon) ** 2
                    )
                    nearest_idx = dists.idxmin()
                    depth_val = bathy_grid.loc[nearest_idx, depth_col]
                    df.at[idx, "depth_m"]          = depth_val
                    sp_list = species_per_hex.get(hex_id, [])
                    df.at[idx, "score_bathymetry"] = _depth_habitat_score(float(depth_val), sp_list)
        except Exception as e:
            logger.warning(f"[CRS] Error calculando score batimetría: {e}")

    # ── 7. Score Upwelling ─────────────────────────────────────────────────
    if upwelling_df is not None and not upwelling_df.empty:
        try:
            import h3 as h3lib
            lat_col = "grid_lat" if "grid_lat" in upwelling_df.columns else "latitude"
            lon_col = "grid_lon" if "grid_lon" in upwelling_df.columns else "longitude"

            upwelling_scores = []
            for _, row in df.iterrows():
                hex_id = row["h3_index"]
                lat, lon = h3lib.cell_to_latlng(hex_id)
                dists = np.sqrt(
                    (upwelling_df[lat_col] - lat) ** 2 +
                    (upwelling_df[lon_col] - lon) ** 2
                )
                nearest_idx = dists.idxmin()
                upwelling_scores.append(upwelling_df.loc[nearest_idx, "upwelling_index"])
            df["score_upwelling"] = upwelling_scores
        except Exception as e:
            logger.warning(f"[CRS] Error calculando score upwelling: {e}")
            df["score_upwelling"] = 0.0
    else:
        df["score_upwelling"] = 0.0

    # ── 8. Composite Risk Score (CRS) ──────────────────────────────────────
    score_cols = {
        "score_co_occurrence": WEIGHTS["co_occurrence"],
        "score_acoustic":      WEIGHTS["acoustic"],
        "score_sst":           WEIGHTS["sst"],
        "score_productivity":  WEIGHTS["productivity"],
        "score_gap_events":    WEIGHTS["gap_events"],
        "score_bathymetry":    WEIGHTS["bathymetry"],
        "score_upwelling":     WEIGHTS["upwelling"],
    }

    df["crs"] = sum(
        df[col] * weight for col, weight in score_cols.items()
    )

    # ── 9. Modificador Temporal (Estacionalidad) ───────────────────────────
    if analysis_month and species_per_hex:
        from src.pipeline.seasonal import get_temporal_risk_modifier

        def _temporal_modifier(hex_id: str) -> float:
            sp_list = species_per_hex.get(hex_id, [])
            if not sp_list:
                return 1.0
            modifiers = [
                get_temporal_risk_modifier(sp, month=analysis_month)
                for sp in sp_list
            ]
            return float(np.max(modifiers))   # usar el mayor modificador

        df["temporal_modifier"] = df["h3_index"].map(_temporal_modifier)
        df["crs"] = df["crs"] * df["temporal_modifier"]
    else:
        df["temporal_modifier"] = 1.0

    # Normalizar CRS a [0, 100] para legibilidad
    crs_max = df["crs"].max()
    if crs_max > 0:
        df["crs_100"] = (df["crs"] / crs_max * 100).round(2)
    else:
        df["crs_100"] = 0.0

    # ── 10. Nivel de Riesgo Categórico ────────────────────────────────────
    def _risk_level(crs_norm: float) -> str:
        if crs_norm >= 75:   return "CRITICAL"
        elif crs_norm >= 50: return "HIGH"
        elif crs_norm >= 25: return "MEDIUM"
        else:                return "LOW"

    df["crs_level"] = df["crs_100"].apply(_risk_level)

    logger.info(
        f"[CRS] Composite Risk Score calculado para {len(df)} celdas | "
        f"CRITICAL: {(df.crs_level == 'CRITICAL').sum()} | "
        f"HIGH: {(df.crs_level == 'HIGH').sum()} | "
        f"MEDIUM: {(df.crs_level == 'MEDIUM').sum()}"
    )
    return df
