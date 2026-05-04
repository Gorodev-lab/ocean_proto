"""
ocean_proto / src / pipeline / acoustic_model.py
================================================
Modelo simplificado de impacto acústico submarino.

Estima el nivel de presión sonora (SPL) en celdas H3 a partir de:
  - Detecciones SAR de embarcaciones (GFW)
  - Tipo de embarcación → nivel de fuente sonora típico
  - Modelo de propagación cilíndrica simplificada

Referencias:
  - NOAA Technical Guidance (2016): Acoustic Threshold Criteria for Marine Mammals
  - Richardson et al. (1995): Marine Mammals and Noise
  - OSPAR (2014): Background Document on Monitoring Impulsive Noise
"""

import logging
import math
import pandas as pd
import numpy as np
from typing import Dict

logger = logging.getLogger(__name__)

# ── Niveles de fuente sonora por tipo de embarcación ─────────────────────────
# Source Level en dB re 1μPa @ 1m (valores medianos literatura científica)
# Fuente: Wales & Heitmeyer (2002), Arveson & Vendittis (2000)
VESSEL_SOURCE_LEVEL_DB: Dict[str, float] = {
    "cargo":      186.0,   # Buque de carga grande
    "tanker":     190.0,   # Tanquero (mayor y más ruidoso)
    "bunker":     182.0,   # Buque abastecedor / bunker
    "fishing":    158.0,   # Pesquero artesanal/industrial
    "support":    175.0,   # OSV / buque de apoyo offshore
    "tug":        170.0,   # Remolcador
    "passenger":  165.0,   # Barco de pasajeros
    "seismic":    225.0,   # Airgun sísmico (estimado en actividad)
    "unknown":    170.0,   # Valor conservador por defecto
}

# ── Umbrales NOAA de perturbación acústica ───────────────────────────────────
# NOAA Technical Guidance (2018) - SPL en dB re 1μPa (RMS, broadband)
# Level A Harassment (potential hearing damage)
LEVEL_A_THRESHOLD_DB: Dict[str, float] = {
    "Cetacea_LF":  179.0,   # Misticetos (ballena azul, gris, jorobada)
    "Cetacea_MF":  178.0,   # Odontocetos de frecuencia media
    "Cetacea_HF":  153.0,   # Odontocetos de frecuencia alta
    "Pinnipeds":   186.0,   # Pinnípedos en agua
}
# Level B Harassment (behavioral disruption)
LEVEL_B_THRESHOLD_DB: Dict[str, float] = {
    "Cetacea":    120.0,
    "Pinnipeds":  120.0,
}

# Mapeo especie → grupo acústico NOAA
SPECIES_ACOUSTIC_GROUP: Dict[str, str] = {
    "Balaenoptera musculus":   "Cetacea_LF",
    "Balaenoptera physalus":   "Cetacea_LF",
    "Balaenoptera borealis":   "Cetacea_LF",
    "Megaptera novaeangliae":  "Cetacea_LF",
    "Eschrichtius robustus":   "Cetacea_LF",
    "Eubalaena japonica":      "Cetacea_LF",
    "Physeter macrocephalus":  "Cetacea_MF",
    "Kogia breviceps":         "Cetacea_MF",
    "Ziphius cavirostris":     "Cetacea_HF",
    "Mesoplodon densirostris": "Cetacea_HF",
    "Rhincodon typus":         "Cetacea_MF",  # no cetáceo, pero similar
    "Manta birostris":         "Cetacea_MF",  # sensible a bajas frecuencias
}

# ── Constantes de propagación ─────────────────────────────────────────────────
# Pérdida de transmisión cilíndrica: TL = 20×log10(r) + α×r
# α = coeficiente de absorción del agua de mar (dB/km a 250 Hz)
ABSORPTION_COEFF_DB_PER_KM = 0.003   # muy baja frecuencia (<500 Hz)
REFERENCE_DISTANCE_M       = 1.0     # distancia de referencia del SL


def transmission_loss(distance_m: float, freq_hz: float = 250.0) -> float:
    """
    Calcula la pérdida de transmisión acústica (TL) en agua de mar.

    Modelo: propagación cilíndrica (adecuado para plataforma continental)
      TL = 20 × log10(r) + α × r  [dB]

    Para aguas profundas usar modelo esférico: 20×log10(r)
    Para aguas someras (<200m): cilíndrico da mejor aproximación.

    Parámetros
    ----------
    distance_m : distancia fuente-receptor en metros
    freq_hz    : frecuencia central en Hz

    Retorna
    -------
    TL en dB (positivo)
    """
    if distance_m <= 0:
        return 0.0
    r_km = distance_m / 1000.0
    # Coeficiente de absorción según frecuencia (simplificado)
    alpha = ABSORPTION_COEFF_DB_PER_KM * (freq_hz / 250.0) ** 0.5
    tl = 20.0 * math.log10(max(distance_m, REFERENCE_DISTANCE_M)) + alpha * r_km
    return tl


def estimate_spl_at_hex(
    vessel_type: str,
    distance_to_center_m: float = 25000.0,  # ~25 km radio medio celda H3-5
) -> float:
    """
    Estima el SPL recibido en el centro de una celda H3 para una embarcación.

    SPL_recibido = SL - TL(r)

    Parámetros
    ----------
    vessel_type         : tipo de embarcación (clave de VESSEL_SOURCE_LEVEL_DB)
    distance_to_center_m: distancia de la embarcación al centro de la celda

    Retorna
    -------
    SPL estimado en dB re 1μPa
    """
    sl = VESSEL_SOURCE_LEVEL_DB.get(vessel_type.lower(), VESSEL_SOURCE_LEVEL_DB["unknown"])
    tl = transmission_loss(distance_to_center_m)
    return max(sl - tl, 0.0)


def compute_acoustic_risk_per_hex(
    gfw_df: pd.DataFrame,
    h3_resolution: int = 5,
) -> pd.DataFrame:
    """
    Calcula el nivel de ruido acumulado y el riesgo acústico para cada
    celda H3 presente en los datos de detección SAR.

    Metodología:
      1. Para cada celda H3, suman las contribuciones energéticas de todos
         los buques detectados (suma coherente en escala lineal, luego a dB).
      2. Se asigna un nivel de riesgo categórico según umbrales NOAA.

    Parámetros
    ----------
    gfw_df        : DataFrame [mmsi, lat, lon, vessel_type, h3_index]
    h3_resolution : resolución H3 usada en la asignación de celdas

    Retorna
    -------
    DataFrame: [h3_index, vessel_count, estimated_spl_db, acoustic_risk_level,
                acoustic_risk_score]
    """
    if gfw_df.empty:
        logger.warning("[Acoustic] gfw_df vacío — sin estimación acústica.")
        return pd.DataFrame(columns=[
            "h3_index", "vessel_count", "estimated_spl_db",
            "acoustic_risk_level", "acoustic_risk_score",
        ])

    # Aseguramos que h3_index existe
    if "h3_index" not in gfw_df.columns:
        try:
            import h3
            gfw_df = gfw_df.copy()
            gfw_df["h3_index"] = gfw_df.apply(
                lambda r: h3.latlng_to_cell(r["lat"], r["lon"], h3_resolution),
                axis=1
            )
        except ImportError:
            logger.error("[Acoustic] h3 no instalado — agrega 'h3' a requirements.txt")
            return pd.DataFrame()

    # Radio aproximado de la celda H3-5 en km (~50 km diámetro → 25 km radio)
    H3_CELL_RADIUS_M = {5: 25000, 6: 9000, 7: 3300}.get(h3_resolution, 25000)

    rows = []
    for hex_id, group in gfw_df.groupby("h3_index"):
        # Suma energética (escala lineal de intensidad acústica)
        total_intensity = 0.0
        for _, row in group.iterrows():
            v_type = str(row.get("vessel_type", "unknown")).lower()
            spl = estimate_spl_at_hex(v_type, H3_CELL_RADIUS_M)
            # Convertir dB a unidades de presión cuadrada (Pa²) y acumular
            total_intensity += 10 ** (spl / 10.0)

        # Reconvertir a dB
        accumulated_spl = 10.0 * math.log10(total_intensity) if total_intensity > 0 else 0.0

        # Clasificar nivel de riesgo según umbrales NOAA (más restrictivo: cetáceos LF)
        if accumulated_spl >= LEVEL_A_THRESHOLD_DB["Cetacea_LF"]:
            risk_level = "CRITICAL"
            risk_score = 4
        elif accumulated_spl >= LEVEL_B_THRESHOLD_DB["Cetacea"]:
            risk_level = "HIGH"
            risk_score = 3
        elif accumulated_spl >= (LEVEL_B_THRESHOLD_DB["Cetacea"] - 20):
            risk_level = "MEDIUM"
            risk_score = 2
        else:
            risk_level = "LOW"
            risk_score = 1

        rows.append({
            "h3_index":             hex_id,
            "vessel_count":         len(group),
            "estimated_spl_db":     round(accumulated_spl, 2),
            "acoustic_risk_level":  risk_level,
            "acoustic_risk_score":  risk_score,
        })

    df_out = pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        "h3_index", "vessel_count", "estimated_spl_db",
        "acoustic_risk_level", "acoustic_risk_score",
    ])
    if not df_out.empty:
        logger.info(
            f"[Acoustic] {len(df_out)} celdas analizadas | "
            f"CRITICAL: {(df_out['acoustic_risk_level'] == 'CRITICAL').sum()} | "
            f"HIGH: {(df_out['acoustic_risk_level'] == 'HIGH').sum()}"
        )
    return df_out



def get_species_threshold(species: str) -> dict:
    """
    Retorna los umbrales NOAA de perturbación para una especie dada.

    Retorna
    -------
    dict: {level_a_db, level_b_db, acoustic_group}
    """
    group = SPECIES_ACOUSTIC_GROUP.get(species, "Cetacea_MF")
    return {
        "level_a_db":     LEVEL_A_THRESHOLD_DB.get(group, 178.0),
        "level_b_db":     LEVEL_B_THRESHOLD_DB.get("Cetacea", 120.0),
        "acoustic_group": group,
    }
