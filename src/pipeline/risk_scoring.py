"""
ocean_proto / src / pipeline / risk_scoring.py — GFW + OBIS
============================================================
Motor del Índice de Presión Antrópica (IPA) con integración de
co-ocurrencia megafauna/embarcaciones (OBIS × GFW).

Criterios y pesos (8 criterios, suma = 1.0):
  w_traffic_density    = 0.20  →  SAR + 4Wings presence (densidad de tráfico)
  w_acoustic           = 0.20  →  SPL acumulado en celda
  w_cooccurrence       = 0.20  →  Co-ocurrencia megafauna × embarcaciones (OBIS)
  w_fishing_effort     = 0.12  →  Horas de pesca (proxy biológico)
  w_behavior_anomaly   = 0.12  →  Gaps + Encounters + Loitering
  w_og_pressure        = 0.08  →  Plataformas + OSVs
  w_corridor_intensity = 0.05  →  Volumen de presencia en ruta
  w_identity_risk      = 0.03  →  Placeholder para Vessel Insights futuro

Todos los sub-scores se normalizan a [0, 1] antes de ponderar.
El IPA final se escala a [0, 100] para compatibilidad con el frontend.

Safe-math garantías:
  - Divisiones por cero protegidas con np.where — nunca ZeroDivisionError.
  - NaN en sub-scores intermedios rellenados con 0.0 antes del IPA.
  - IPA_100 acotado estrictamente a [0, 100].
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Pesos del IPA (8 criterios) ───────────────────────────────────────────────
WEIGHTS: Dict[str, float] = {
    "traffic_density":    0.20,
    "acoustic":           0.20,
    "cooccurrence":       0.20,   # NUEVO — co-ocurrencia OBIS × GFW
    "fishing_effort":     0.12,
    "behavior_anomaly":   0.12,
    "og_pressure":        0.08,
    "corridor_intensity": 0.05,
    "identity_risk":      0.03,
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, (
    f"Los pesos deben sumar 1.0; suma actual = {sum(WEIGHTS.values()):.10f}"
)


# ── Helpers vectorizados ──────────────────────────────────────────────────────

def _minmax_series(s: pd.Series) -> pd.Series:
    """
    Normaliza una Serie al rango [0, 1] usando min-max scaling vectorizado.

    Si max == min (varianza cero, todos los valores son iguales), retorna
    una Serie de ceros para evitar 0/0. Usa np.where para garantizar
    safe-math sin bucles Python.
    """
    s_min = s.min()
    s_max = s.max()
    rng = s_max - s_min
    normalized = np.where(rng > 0, (s - s_min) / rng, 0.0)
    return pd.Series(normalized, index=s.index).clip(0.0, 1.0)


def _map_fill(index_series: pd.Series, mapping: dict, fill: float = 0.0) -> pd.Series:
    """
    Mapea una Serie de claves a valores usando un diccionario y rellena
    los valores faltantes con ``fill``.

    Reemplaza el patrón ``apply(lambda h: d.get(h, 0))`` por una
    operación vectorizada de Pandas.
    """
    return index_series.map(mapping).fillna(fill)


# ── Motor principal ───────────────────────────────────────────────────────────

def compute_anthropic_pressure_index(
    hotspots_df:        pd.DataFrame,
    acoustic_df:        Optional[pd.DataFrame] = None,
    gaps_hex_df:        Optional[pd.DataFrame] = None,
    encounters_hex_df:  Optional[pd.DataFrame] = None,
    loitering_hex_df:   Optional[pd.DataFrame] = None,
    fishing_effort_df:  Optional[pd.DataFrame] = None,
    presence_df:        Optional[pd.DataFrame] = None,
    platforms_hex_df:   Optional[pd.DataFrame] = None,
    support_hex_df:     Optional[pd.DataFrame] = None,
    megafauna_hex_df:   Optional[pd.DataFrame] = None,
    analysis_month:     Optional[int] = None,
) -> pd.DataFrame:
    """
    Calcula el Índice de Presión Antrópica (IPA) para cada celda H3.

    Parameters
    ----------
    hotspots_df       : DataFrame base con columnas [h3_index, vessel_count].
    acoustic_df       : [h3_index, estimated_spl_db, acoustic_risk_score].
    gaps_hex_df       : [h3_index, gap_count].
    encounters_hex_df : [h3_index, encounter_count].
    loitering_hex_df  : [h3_index, loitering_count].
    fishing_effort_df : [h3_index, fishing_hours] o [lat, lon, fishing_hours].
    presence_df       : [h3_index, hours].
    platforms_hex_df  : [h3_index, platform_count].
    support_hex_df    : [h3_index, support_count].
    megafauna_hex_df  : [h3_index, megafauna_count]  ← NUEVO (OBIS).
    analysis_month    : mes para modificador temporal (1-12).

    Returns
    -------
    pd.DataFrame con columnas:
        h3_index, vessel_count, megafauna_count, ipa, ipa_100, ipa_level,
        score_* (8 sub-scores), crs_100, crs_level, risk_score.
    """
    if hotspots_df is None or hotspots_df.empty:
        logger.warning("[IPA] hotspots_df vacío — sin índice de presión.")
        return pd.DataFrame()

    df = hotspots_df.copy()
    df["h3_index"] = df["h3_index"].astype(str)

    # ── 1. Score de Densidad de Tráfico ────────────────────────────────────
    #    Base: vessel_count normalizado; enriquecido con 4Wings presence.
    df["vessel_count"] = pd.to_numeric(
        df.get("vessel_count", 0), errors="coerce"
    ).fillna(0.0)

    traffic_base = _minmax_series(df["vessel_count"])

    if (
        presence_df is not None
        and not presence_df.empty
        and "h3_index" in presence_df.columns
        and "hours" in presence_df.columns
    ):
        pres_map: dict = presence_df.groupby("h3_index")["hours"].sum().to_dict()
        pres_raw = _map_fill(df["h3_index"], pres_map)
        pres_scores = _minmax_series(pres_raw)
        # Promedio ponderado: 60% SAR + 40% AIS presence
        df["score_traffic_density"] = 0.6 * traffic_base + 0.4 * pres_scores
    else:
        df["score_traffic_density"] = traffic_base

    # ── 2. Score Acústico ──────────────────────────────────────────────────
    if acoustic_df is not None and not acoustic_df.empty and "h3_index" in acoustic_df.columns:
        acoustic_map: dict = (
            acoustic_df.set_index("h3_index")["acoustic_risk_score"].to_dict()
        )
        spl_map: dict = (
            acoustic_df.set_index("h3_index")["estimated_spl_db"].to_dict()
        )
        raw_acoustic = _map_fill(df["h3_index"], acoustic_map)
        df["score_acoustic"]   = _minmax_series(raw_acoustic)
        df["estimated_spl_db"] = _map_fill(df["h3_index"], spl_map)
    else:
        df["score_acoustic"]   = 0.0
        df["estimated_spl_db"] = 0.0

    # ── 3. Score de Co-ocurrencia Megafauna × Embarcaciones (OBIS) ────────
    #
    # Fórmula:
    #   product_i = vessel_count_i × megafauna_count_i
    #   cooccurrence_i = product_i / max(product across all cells)
    #
    # Safe-math: np.where garantiza cooccurrence = 0.0 cuando el
    # denominador es 0 (OBIS vacío o sin embarcaciones), sin raise.

    # Obtener megafauna_count por celda H3
    if (
        megafauna_hex_df is not None
        and not megafauna_hex_df.empty
        and "h3_index" in megafauna_hex_df.columns
        and "megafauna_count" in megafauna_hex_df.columns
    ):
        meg_map: dict = (
            megafauna_hex_df.set_index("h3_index")["megafauna_count"].to_dict()
        )
        df["megafauna_count"] = _map_fill(df["h3_index"], meg_map, fill=0.0)
    else:
        # OBIS no disponible o vacío — degradación silenciosa
        df["megafauna_count"] = 0.0
        logger.debug(
            "[IPA] megafauna_hex_df no disponible. "
            "score_cooccurrence = 0.0 para todas las celdas."
        )

    # Producto cruzado vectorizado
    product = df["vessel_count"].astype(float) * df["megafauna_count"].astype(float)
    max_product = float(product.max())

    # División segura: np.where evita ZeroDivisionError en un solo pase C
    df["score_cooccurrence"] = np.where(
        max_product > 0.0,
        (product / max_product).clip(0.0, 1.0),
        0.0,
    )

    logger.info(
        f"[IPA] Co-ocurrencia — max_product={max_product:.1f} | "
        f"celdas con megafauna: {(df['megafauna_count'] > 0).sum()}"
    )

    # ── 4. Score de Esfuerzo Pesquero (proxy biológico) ────────────────────
    df["score_fishing_effort"] = 0.0
    df["fishing_hours"]        = 0.0

    if fishing_effort_df is not None and not fishing_effort_df.empty:
        if "h3_index" in fishing_effort_df.columns and "fishing_hours" in fishing_effort_df.columns:
            effort_map: dict = (
                fishing_effort_df.groupby("h3_index")["fishing_hours"].sum().to_dict()
            )
        elif "lat" in fishing_effort_df.columns and "lon" in fishing_effort_df.columns:
            effort_map = _assign_h3_effort(fishing_effort_df)
        else:
            effort_map = {}

        if effort_map:
            raw_effort = _map_fill(df["h3_index"], effort_map)
            df["fishing_hours"]        = raw_effort
            df["score_fishing_effort"] = _minmax_series(raw_effort)

    # ── 5. Score de Anomalías de Comportamiento ───────────────────────────
    #    Compuesto: gaps 50% + encounters 30% + loitering 20%

    if gaps_hex_df is not None and not gaps_hex_df.empty and "h3_index" in gaps_hex_df.columns:
        gap_map: dict = gaps_hex_df.set_index("h3_index")["gap_count"].to_dict()
        raw_gaps = _map_fill(df["h3_index"], gap_map)
        gap_scores = _minmax_series(raw_gaps)
        df["gap_count"] = raw_gaps
    else:
        gap_scores    = pd.Series(0.0, index=df.index)
        df["gap_count"] = 0

    if encounters_hex_df is not None and not encounters_hex_df.empty and "h3_index" in encounters_hex_df.columns:
        enc_map: dict = encounters_hex_df.set_index("h3_index")["encounter_count"].to_dict()
        raw_enc = _map_fill(df["h3_index"], enc_map)
        enc_scores = _minmax_series(raw_enc)
        df["encounter_count"] = raw_enc
    else:
        enc_scores          = pd.Series(0.0, index=df.index)
        df["encounter_count"] = 0

    if loitering_hex_df is not None and not loitering_hex_df.empty and "h3_index" in loitering_hex_df.columns:
        loi_map: dict = loitering_hex_df.set_index("h3_index")["loitering_count"].to_dict()
        raw_loi = _map_fill(df["h3_index"], loi_map)
        loi_scores = _minmax_series(raw_loi)
        df["loitering_count"] = raw_loi
    else:
        loi_scores           = pd.Series(0.0, index=df.index)
        df["loitering_count"] = 0

    df["score_behavior_anomaly"] = (
        0.50 * gap_scores + 0.30 * enc_scores + 0.20 * loi_scores
    )

    # ── 6. Score de Presión O&G ───────────────────────────────────────────
    if platforms_hex_df is not None and not platforms_hex_df.empty and "h3_index" in platforms_hex_df.columns:
        plat_map: dict = platforms_hex_df.set_index("h3_index")["platform_count"].to_dict()
        raw_plat = _map_fill(df["h3_index"], plat_map)
        plat_scores        = _minmax_series(raw_plat)
        df["platform_count"] = raw_plat
    else:
        plat_scores          = pd.Series(0.0, index=df.index)
        df["platform_count"] = 0

    if support_hex_df is not None and not support_hex_df.empty and "h3_index" in support_hex_df.columns:
        supp_map: dict = support_hex_df.set_index("h3_index")["support_count"].to_dict()
        raw_supp = _map_fill(df["h3_index"], supp_map)
        supp_scores        = _minmax_series(raw_supp)
        df["support_count"] = raw_supp
    else:
        supp_scores         = pd.Series(0.0, index=df.index)
        df["support_count"] = 0

    df["score_og_pressure"] = 0.6 * plat_scores + 0.4 * supp_scores

    # ── 7. Score de Intensidad de Corredor ─────────────────────────────────
    #    Deriva del traffic score; en futuro: port visits + rutas AIS
    df["score_corridor_intensity"] = df["score_traffic_density"]

    # ── 8. Score de Riesgo por Identidad (placeholder) ─────────────────────
    #    Futuro: Vessel Insights API (IUU flags, PSMA violations)
    df["score_identity_risk"] = 0.0

    # ── IPA — Suma ponderada de los 8 criterios ───────────────────────────
    #
    # Garantía NaN-safe: .fillna(0.0) en cada columna de score antes de
    # ponderar, evitando que un sub-score con NaN contamine el IPA final.

    score_cols: dict[str, float] = {
        "score_traffic_density":    WEIGHTS["traffic_density"],
        "score_acoustic":           WEIGHTS["acoustic"],
        "score_cooccurrence":       WEIGHTS["cooccurrence"],
        "score_fishing_effort":     WEIGHTS["fishing_effort"],
        "score_behavior_anomaly":   WEIGHTS["behavior_anomaly"],
        "score_og_pressure":        WEIGHTS["og_pressure"],
        "score_corridor_intensity": WEIGHTS["corridor_intensity"],
        "score_identity_risk":      WEIGHTS["identity_risk"],
    }

    # Relleno defensivo de NaN antes del cálculo final
    for col in score_cols:
        df[col] = df[col].fillna(0.0)

    df["ipa"] = sum(
        df[col] * weight for col, weight in score_cols.items()
    )

    # ── Modificador Temporal (estacionalidad de pesca) ─────────────────────
    if analysis_month and fishing_effort_df is not None and not fishing_effort_df.empty:
        try:
            from src.pipeline.seasonal import get_fishing_season_modifier
            df["temporal_modifier"] = get_fishing_season_modifier(analysis_month)
            df["ipa"] = (df["ipa"] * df["temporal_modifier"]).clip(0.0, 1.0)
        except Exception as exc:
            logger.warning(f"[IPA] Modificador temporal no disponible: {exc}")
            df["temporal_modifier"] = 1.0
    else:
        df["temporal_modifier"] = 1.0

    # ── Escalar IPA a [0, 100] con safe-math ─────────────────────────────
    ipa_max = float(df["ipa"].max())
    df["ipa_100"] = np.where(
        ipa_max > 0.0,
        (df["ipa"] / ipa_max * 100.0).clip(0.0, 100.0).round(2),
        0.0,
    )

    # ── Nivel de Presión Categórico (vectorizado con pd.cut) ───────────────
    df["ipa_level"] = pd.cut(
        df["ipa_100"],
        bins=[-np.inf, 25.0, 50.0, 75.0, np.inf],
        labels=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
        right=True,
    ).astype(str)

    # Aliases para compatibilidad con frontend y endpoints existentes
    df["risk_score"] = df["ipa"]
    df["crs_100"]    = df["ipa_100"]
    df["crs_level"]  = df["ipa_level"]

    logger.info(
        f"[IPA] Calculado para {len(df)} celdas | "
        f"CRITICAL: {(df.ipa_level == 'CRITICAL').sum()} | "
        f"HIGH: {(df.ipa_level == 'HIGH').sum()} | "
        f"MEDIUM: {(df.ipa_level == 'MEDIUM').sum()} | "
        f"Celdas con co-ocurrencia activa: {(df['score_cooccurrence'] > 0).sum()}"
    )
    return df


# ── Helper interno: asignar H3 a esfuerzo pesquero lat/lon ───────────────────

def _assign_h3_effort(fishing_effort_df: pd.DataFrame) -> dict:
    """
    Asigna celdas H3 a registros de esfuerzo pesquero cuando el DataFrame
    no tiene la columna ``h3_index`` pero sí tiene ``lat`` y ``lon``.

    Retorna un diccionario {h3_index: total_fishing_hours}.
    """
    try:
        import h3 as h3lib
        from src.pipeline.spatial_join import H3_RESOLUTION

        _df = fishing_effort_df.copy()

        # Vectorizado: construir Series de h3_index con apply (operación
        # única sobre H3, no por fila del DataFrame principal)
        valid_mask = _df["lat"].notna() & _df["lon"].notna()
        _df = _df[valid_mask].copy()

        if _df.empty:
            return {}

        _df["h3_index"] = [
            h3lib.latlng_to_cell(lat, lon, H3_RESOLUTION)
            for lat, lon in zip(_df["lat"], _df["lon"])
        ]
        return _df.groupby("h3_index")["fishing_hours"].sum().to_dict()

    except Exception as exc:
        logger.warning(f"[IPA] Error asignando H3 a fishing_effort: {exc}")
        return {}


# ── Función auxiliar pública: agregar megafauna por celda H3 ──────────────────

def aggregate_megafauna_by_hex(
    obis_gdf,
    resolution: int = 5,
) -> pd.DataFrame:
    """
    Agrega conteos de avistamientos de megafauna (OBIS) por celda H3.

    Esta función es el puente entre el GeoDataFrame de OBIS producido por
    ``ingest.py`` y el parámetro ``megafauna_hex_df`` de
    ``compute_anthropic_pressure_index``.

    Parameters
    ----------
    obis_gdf   : GeoDataFrame con columna ``geometry`` (Points) y
                 opcionalmente ``taxa_group`` y ``oil_relevance``.
    resolution : resolución H3 (default 5 ≈ 50 km).

    Returns
    -------
    pd.DataFrame con columnas [h3_index, megafauna_count].
    Retorna DataFrame vacío si la entrada está vacía.
    """
    if obis_gdf is None or (hasattr(obis_gdf, "empty") and obis_gdf.empty):
        return pd.DataFrame(columns=["h3_index", "megafauna_count"])

    try:
        import h3 as h3lib

        _df = obis_gdf.copy()

        # Extraer lat/lon desde geometría o columnas directas
        if "geometry" in _df.columns and hasattr(_df["geometry"].iloc[0], "y"):
            lats = _df["geometry"].apply(lambda p: p.y if p else None)
            lons = _df["geometry"].apply(lambda p: p.x if p else None)
        elif "decimalLatitude" in _df.columns:
            lats = pd.to_numeric(_df["decimalLatitude"], errors="coerce")
            lons = pd.to_numeric(_df["decimalLongitude"], errors="coerce")
        elif "lat" in _df.columns:
            lats = pd.to_numeric(_df["lat"], errors="coerce")
            lons = pd.to_numeric(_df["lon"], errors="coerce")
        else:
            logger.warning("[IPA] aggregate_megafauna_by_hex: sin columnas lat/lon.")
            return pd.DataFrame(columns=["h3_index", "megafauna_count"])

        valid = lats.notna() & lons.notna()
        _df = _df[valid].copy()
        lats = lats[valid]
        lons = lons[valid]

        if _df.empty:
            return pd.DataFrame(columns=["h3_index", "megafauna_count"])

        # Asignación H3 vectorizada (list comprehension en nivel Python,
        # único recorrido posible ya que h3lib no expone API NumPy)
        _df["h3_index"] = [
            h3lib.latlng_to_cell(float(lat), float(lon), resolution)
            for lat, lon in zip(lats, lons)
        ]

        result = (
            _df.groupby("h3_index")
            .size()
            .reset_index(name="megafauna_count")
        )
        logger.info(
            f"[IPA] Megafauna agregada: {len(result)} celdas H3 | "
            f"{result['megafauna_count'].sum():.0f} avistamientos totales."
        )
        return result

    except Exception as exc:
        logger.error(f"[IPA] Error en aggregate_megafauna_by_hex: {exc}")
        return pd.DataFrame(columns=["h3_index", "megafauna_count"])
