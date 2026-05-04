"""
ocean_proto / src / pipeline / risk_scoring.py — GFW-ONLY
=========================================================
Motor de Índice de Presión Antrópica (IPA) usando exclusivamente datos GFW.

A diferencia del CRS (Composite Risk Score) del pipeline combinado que usa
datos biológicos de OBIS y oceanográficos de ERDDAP, el IPA mide la
intensidad de actividad humana por celda H3 como proxy de riesgo.

Criterios y pesos:
  w_traffic_density   = 0.25  →  SAR + 4Wings presence (densidad de tráfico)
  w_acoustic           = 0.20  →  SPL acumulado en celda
  w_fishing_effort     = 0.15  →  Horas de pesca (proxy biológico)
  w_behavior_anomaly   = 0.15  →  Gaps + Encounters + Loitering
  w_og_pressure        = 0.10  →  Plataformas + OSVs
  w_corridor_intensity = 0.10  →  Volumen de presencia en ruta
  w_identity_risk      = 0.05  →  Placeholder para Vessel Insights futuro

Todos los scores se normalizan a [0, 1] antes de ponderar.
"""

import logging
import math
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ── Pesos del IPA ─────────────────────────────────────────────────────────────
WEIGHTS: Dict[str, float] = {
    "traffic_density":    0.25,
    "acoustic":           0.20,
    "fishing_effort":     0.15,
    "behavior_anomaly":   0.15,
    "og_pressure":        0.10,
    "corridor_intensity": 0.10,
    "identity_risk":      0.05,
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Los pesos deben sumar 1.0"


# ── Funciones de normalización ────────────────────────────────────────────────

def _normalize_minmax(value: float, min_val: float, max_val: float) -> float:
    """Normaliza un valor al rango [0, 1] usando min-max scaling."""
    if max_val == min_val:
        return 0.0
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))


# ── Motor principal ───────────────────────────────────────────────────────────

def compute_anthropic_pressure_index(
    hotspots_df:        pd.DataFrame,
    acoustic_df:        pd.DataFrame = None,
    gaps_hex_df:        pd.DataFrame = None,
    encounters_hex_df:  pd.DataFrame = None,
    loitering_hex_df:   pd.DataFrame = None,
    fishing_effort_df:  pd.DataFrame = None,
    presence_df:        pd.DataFrame = None,
    platforms_hex_df:   pd.DataFrame = None,
    support_hex_df:     pd.DataFrame = None,
    analysis_month:     Optional[int] = None,
) -> pd.DataFrame:
    """
    Calcula el Índice de Presión Antrópica (IPA) para cada celda H3.

    Parámetros
    ----------
    hotspots_df       : DataFrame base [h3_index, vessel_count]
    acoustic_df       : DataFrame [h3_index, estimated_spl_db, acoustic_risk_score]
    gaps_hex_df       : DataFrame [h3_index, gap_count]
    encounters_hex_df : DataFrame [h3_index, encounter_count]
    loitering_hex_df  : DataFrame [h3_index, loitering_count]
    fishing_effort_df : DataFrame [h3_index, fishing_hours]
    presence_df       : DataFrame [h3_index, hours]
    platforms_hex_df  : DataFrame [h3_index, platform_count]
    support_hex_df    : DataFrame [h3_index, support_count]
    analysis_month    : mes para modificador temporal (1-12)

    Retorna
    -------
    DataFrame: [h3_index, ipa, ipa_100, ipa_level, ...sub-scores...]
    """
    if hotspots_df.empty:
        logger.warning("[IPA] hotspots_df vacío — sin índice de presión.")
        return pd.DataFrame()

    df = hotspots_df.copy()
    df["h3_index"] = df["h3_index"].astype(str)

    # ── 1. Score de Densidad de Tráfico ────────────────────────────────────
    max_vc = df["vessel_count"].max()
    df["score_traffic_density"] = df["vessel_count"].apply(
        lambda x: _normalize_minmax(x, 0, max_vc) if max_vc > 0 else 0.0
    )

    # Enriquecer con 4Wings presence si disponible
    if presence_df is not None and not presence_df.empty and "h3_index" in presence_df.columns:
        pres_map = presence_df.groupby("h3_index")["hours"].sum().to_dict()
        max_pres = max(pres_map.values()) if pres_map else 1
        pres_scores = df["h3_index"].map(
            lambda h: _normalize_minmax(pres_map.get(h, 0), 0, max_pres)
        )
        # Promedio ponderado: 60% SAR + 40% AIS presence
        df["score_traffic_density"] = (
            0.6 * df["score_traffic_density"] + 0.4 * pres_scores
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

    # ── 3. Score de Esfuerzo Pesquero (proxy biológico) ────────────────────
    df["score_fishing_effort"] = 0.0
    df["fishing_hours"]        = 0.0

    if fishing_effort_df is not None and not fishing_effort_df.empty:
        if "h3_index" in fishing_effort_df.columns:
            effort_map = fishing_effort_df.groupby("h3_index")["fishing_hours"].sum().to_dict()
        elif "lat" in fishing_effort_df.columns and "lon" in fishing_effort_df.columns:
            # Asignar celdas H3 al esfuerzo pesquero
            try:
                import h3 as h3lib
                from src.pipeline.spatial_join import H3_RESOLUTION
                fishing_effort_df = fishing_effort_df.copy()
                fishing_effort_df["h3_index"] = fishing_effort_df.apply(
                    lambda r: h3lib.latlng_to_cell(r["lat"], r["lon"], H3_RESOLUTION)
                    if pd.notna(r.get("lat")) and pd.notna(r.get("lon")) else "",
                    axis=1
                )
                effort_map = fishing_effort_df.groupby("h3_index")["fishing_hours"].sum().to_dict()
            except Exception:
                effort_map = {}
        else:
            effort_map = {}

        if effort_map:
            max_effort = max(effort_map.values())
            df["fishing_hours"] = df["h3_index"].map(lambda h: effort_map.get(h, 0))
            df["score_fishing_effort"] = df["h3_index"].map(
                lambda h: _normalize_minmax(effort_map.get(h, 0), 0, max_effort)
            )

    # ── 4. Score de Anomalías de Comportamiento ───────────────────────────
    # Compuesto de: gaps + encounters + loitering
    gap_scores = pd.Series(0.0, index=df.index)
    enc_scores = pd.Series(0.0, index=df.index)
    loi_scores = pd.Series(0.0, index=df.index)

    if gaps_hex_df is not None and not gaps_hex_df.empty and "h3_index" in gaps_hex_df.columns:
        gap_map = gaps_hex_df.set_index("h3_index")["gap_count"].to_dict()
        max_gaps = max(gap_map.values()) if gap_map else 1
        gap_scores = df["h3_index"].map(
            lambda h: _normalize_minmax(gap_map.get(h, 0), 0, max_gaps)
        )
        df["gap_count"] = df["h3_index"].map(lambda h: gap_map.get(h, 0))
    else:
        df["gap_count"] = 0

    if encounters_hex_df is not None and not encounters_hex_df.empty and "h3_index" in encounters_hex_df.columns:
        enc_map = encounters_hex_df.set_index("h3_index")["encounter_count"].to_dict()
        max_enc = max(enc_map.values()) if enc_map else 1
        enc_scores = df["h3_index"].map(
            lambda h: _normalize_minmax(enc_map.get(h, 0), 0, max_enc)
        )
        df["encounter_count"] = df["h3_index"].map(lambda h: enc_map.get(h, 0))
    else:
        df["encounter_count"] = 0

    if loitering_hex_df is not None and not loitering_hex_df.empty and "h3_index" in loitering_hex_df.columns:
        loi_map = loitering_hex_df.set_index("h3_index")["loitering_count"].to_dict()
        max_loi = max(loi_map.values()) if loi_map else 1
        loi_scores = df["h3_index"].map(
            lambda h: _normalize_minmax(loi_map.get(h, 0), 0, max_loi)
        )
        df["loitering_count"] = df["h3_index"].map(lambda h: loi_map.get(h, 0))
    else:
        df["loitering_count"] = 0

    # Peso interno: gaps 50%, encounters 30%, loitering 20%
    df["score_behavior_anomaly"] = (
        0.50 * gap_scores + 0.30 * enc_scores + 0.20 * loi_scores
    )

    # ── 5. Score de Presión O&G ───────────────────────────────────────────
    og_scores = pd.Series(0.0, index=df.index)

    if platforms_hex_df is not None and not platforms_hex_df.empty and "h3_index" in platforms_hex_df.columns:
        plat_map = platforms_hex_df.set_index("h3_index")["platform_count"].to_dict()
        max_plat = max(plat_map.values()) if plat_map else 1
        plat_scores = df["h3_index"].map(
            lambda h: _normalize_minmax(plat_map.get(h, 0), 0, max_plat)
        )
        df["platform_count"] = df["h3_index"].map(lambda h: plat_map.get(h, 0))
    else:
        plat_scores = pd.Series(0.0, index=df.index)
        df["platform_count"] = 0

    if support_hex_df is not None and not support_hex_df.empty and "h3_index" in support_hex_df.columns:
        supp_map = support_hex_df.set_index("h3_index")["support_count"].to_dict()
        max_supp = max(supp_map.values()) if supp_map else 1
        supp_scores = df["h3_index"].map(
            lambda h: _normalize_minmax(supp_map.get(h, 0), 0, max_supp)
        )
        df["support_count"] = df["h3_index"].map(lambda h: supp_map.get(h, 0))
    else:
        supp_scores = pd.Series(0.0, index=df.index)
        df["support_count"] = 0

    df["score_og_pressure"] = 0.6 * plat_scores + 0.4 * supp_scores

    # ── 6. Score de Intensidad de Corredor ─────────────────────────────────
    # Usa el score de tráfico como base (en futuro: port visits + rutas)
    df["score_corridor_intensity"] = df["score_traffic_density"]

    # ── 7. Score de Riesgo por Identidad (placeholder) ─────────────────────
    # En futuro: Vessel Insights API (IUU flags, PSMA violations)
    df["score_identity_risk"] = 0.0

    # ── 8. Índice de Presión Antrópica (IPA) ──────────────────────────────
    score_cols = {
        "score_traffic_density":    WEIGHTS["traffic_density"],
        "score_acoustic":           WEIGHTS["acoustic"],
        "score_fishing_effort":     WEIGHTS["fishing_effort"],
        "score_behavior_anomaly":   WEIGHTS["behavior_anomaly"],
        "score_og_pressure":        WEIGHTS["og_pressure"],
        "score_corridor_intensity": WEIGHTS["corridor_intensity"],
        "score_identity_risk":      WEIGHTS["identity_risk"],
    }

    df["ipa"] = sum(
        df[col] * weight for col, weight in score_cols.items()
    )

    # ── 9. Modificador Temporal (estacionalidad de pesca) ─────────────────
    if analysis_month and fishing_effort_df is not None and not fishing_effort_df.empty:
        from src.pipeline.seasonal import get_fishing_season_modifier
        df["temporal_modifier"] = get_fishing_season_modifier(analysis_month)
        df["ipa"] = df["ipa"] * df["temporal_modifier"]
    else:
        df["temporal_modifier"] = 1.0

    # Normalizar IPA a [0, 100]
    ipa_max = df["ipa"].max()
    if ipa_max > 0:
        df["ipa_100"] = (df["ipa"] / ipa_max * 100).round(2)
    else:
        df["ipa_100"] = 0.0

    # ── 10. Nivel de Presión Categórico ───────────────────────────────────
    def _pressure_level(ipa_norm: float) -> str:
        if ipa_norm >= 75:   return "CRITICAL"
        elif ipa_norm >= 50: return "HIGH"
        elif ipa_norm >= 25: return "MEDIUM"
        else:                return "LOW"

    df["ipa_level"] = df["ipa_100"].apply(_pressure_level)

    # Alias para compatibilidad con el frontend existente
    df["risk_score"] = df["ipa"]
    df["crs_100"]    = df["ipa_100"]
    df["crs_level"]  = df["ipa_level"]

    logger.info(
        f"[IPA] Índice de Presión Antrópica calculado para {len(df)} celdas | "
        f"CRITICAL: {(df.ipa_level == 'CRITICAL').sum()} | "
        f"HIGH: {(df.ipa_level == 'HIGH').sum()} | "
        f"MEDIUM: {(df.ipa_level == 'MEDIUM').sum()}"
    )
    return df
