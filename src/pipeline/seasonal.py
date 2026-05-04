"""
ocean_proto / src / pipeline / seasonal.py
==========================================
Criterio de estacionalidad y ventanas migratorias.

Define las ventanas temporales de alta presencia de megafauna marina
en el Golfo de California y Baja California Sur, y calcula modificadores
de riesgo estacional para cada especie.

Fuentes de referencia:
  - Tershy et al. (1993): Blue whales in Gulf of California (peak: Dec-Apr)
  - Urbán et al. (2005): Humpback whales in Mexican Pacific (peak: Dec-Mar)
  - Rice et al. (1981): Gray whales migration (peak lagoons: Jan-Mar)
  - Ketchum et al. (2013): Whale sharks in El Golfo / Sea of Cortez (Oct-Feb)
  - Notarbartolo di Sciara (2020): Giant manta aggregations (year-round, peak Dec-May)
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── Ventanas migratorias por especie ─────────────────────────────────────────
# peak_months: lista de meses (1=enero) con máxima presencia en el área BCS/GoC
# breeding: si True, es además época de reproducción/cría → vulnerabilidad extra
# region_note: notas sobre la distribución estacional en el área de estudio
MIGRATION_WINDOWS = {
    "Balaenoptera musculus": {
        "peak_months":    [12, 1, 2, 3, 4],
        "breeding":       False,
        "region_note":    "Golfo de California norte; feeding grounds invernales",
        "risk_multiplier_peak":    2.5,
        "risk_multiplier_offpeak": 0.3,
    },
    "Balaenoptera physalus": {
        "peak_months":    [11, 12, 1, 2, 3],
        "breeding":       False,
        "region_note":    "Canal de Ballenas, Baja California",
        "risk_multiplier_peak":    2.0,
        "risk_multiplier_offpeak": 0.4,
    },
    "Balaenoptera borealis": {
        "peak_months":    [10, 11, 12, 1, 2],
        "breeding":       False,
        "region_note":    "Pacífico BCS y Golfo; presencia invernal ocasional",
        "risk_multiplier_peak":    1.8,
        "risk_multiplier_offpeak": 0.5,
    },
    "Megaptera novaeangliae": {
        "peak_months":    [12, 1, 2, 3],
        "breeding":       True,   # época de cría/apareamiento en BCS
        "region_note":    "Pacífico BCS; apareamiento y nacimientos dic-mar",
        "risk_multiplier_peak":    3.0,   # máxima vulnerabilidad: madres + crías
        "risk_multiplier_offpeak": 0.3,
    },
    "Eschrichtius robustus": {
        "peak_months":    [1, 2, 3],
        "breeding":       True,   # lagunas de reproducción (Scammon, San Ignacio)
        "region_note":    "Lagunas de Baja: Laguna Ojo de Liebre, San Ignacio; presencia altísima",
        "risk_multiplier_peak":    3.5,   # máxima: lagunas de cría confinadas
        "risk_multiplier_offpeak": 0.1,
    },
    "Eubalaena japonica": {
        "peak_months":    [1, 2, 3],
        "breeding":       True,
        "region_note":    "Extremadamente rara; EN crítico; cualquier detección es alta prioridad",
        "risk_multiplier_peak":    5.0,   # especie en peligro crítico
        "risk_multiplier_offpeak": 1.0,   # incluso fuera de temporada
    },
    "Physeter macrocephalus": {
        "peak_months":    [4, 5, 6, 7, 8, 9, 10],   # más común en verano-otoño
        "breeding":       False,
        "region_note":    "Golfo de California; grupos de machos residentes",
        "risk_multiplier_peak":    1.5,
        "risk_multiplier_offpeak": 0.8,
    },
    "Kogia breviceps": {
        "peak_months":    list(range(1, 13)),   # residente todo el año
        "breeding":       False,
        "region_note":    "Aguas profundas del Golfo; residente",
        "risk_multiplier_peak":    1.0,
        "risk_multiplier_offpeak": 1.0,
    },
    "Ziphius cavirostris": {
        "peak_months":    list(range(1, 13)),   # residente todo el año
        "breeding":       False,
        "region_note":    "Cañones submarinos del Golfo; muy vulnerable a sonar",
        "risk_multiplier_peak":    1.0,
        "risk_multiplier_offpeak": 1.0,
    },
    "Mesoplodon densirostris": {
        "peak_months":    list(range(1, 13)),
        "breeding":       False,
        "region_note":    "Aguas profundas; sensible a MFAS/sonar militar",
        "risk_multiplier_peak":    1.0,
        "risk_multiplier_offpeak": 1.0,
    },
    "Rhincodon typus": {
        "peak_months":    [9, 10, 11, 12, 1, 2],
        "breeding":       False,
        "region_note":    "Norte del Golfo (La Paz, Bahía de los Ángeles); agregaciones otoño-invierno",
        "risk_multiplier_peak":    2.0,
        "risk_multiplier_offpeak": 0.5,
    },
    "Manta birostris": {
        "peak_months":    [12, 1, 2, 3, 4, 5],
        "breeding":       False,
        "region_note":    "Pacífico BCS e islas del Golfo; agregaciones invernales-primaverales",
        "risk_multiplier_peak":    1.8,
        "risk_multiplier_offpeak": 0.6,
    },
}


def is_peak_season(species: str, month: int) -> bool:
    """
    Determina si un mes dado está dentro de la temporada pico
    de una especie.

    Parámetros
    ----------
    species : nombre científico de la especie
    month   : número de mes (1-12)

    Retorna
    -------
    True si está en temporada pico
    """
    info = MIGRATION_WINDOWS.get(species)
    if info is None:
        return False
    return month in info["peak_months"]


def get_temporal_risk_modifier(
    species: str,
    event_date: Optional[str] = None,
    month: Optional[int] = None,
) -> float:
    """
    Calcula el modificador de riesgo temporal para una especie en un momento dado.

    El modificador amplifica o reduce el composite risk score según si
    el evento ocurre en temporada pico de la especie.

    Parámetros
    ----------
    species    : nombre científico
    event_date : fecha ISO string (si se provee, extrae el mes automáticamente)
    month      : mes (1-12), alternativa a event_date

    Retorna
    -------
    float: multiplicador de riesgo
      - > 1.0 → temporada pico (mayor riesgo)
      - < 1.0 → fuera de temporada
      - 1.0   → especie residente / sin estacionalidad
    """
    info = MIGRATION_WINDOWS.get(species)
    if info is None:
        logger.debug(f"[Seasonal] Especie desconocida: {species} — usando modificador 1.0")
        return 1.0

    # Extraer mes
    if month is None and event_date:
        try:
            dt = datetime.fromisoformat(str(event_date).split("T")[0])
            month = dt.month
        except (ValueError, TypeError):
            logger.warning(f"[Seasonal] No se pudo parsear fecha: {event_date}")
            return 1.0

    if month is None:
        return 1.0

    if month in info["peak_months"]:
        multiplier = info.get("risk_multiplier_peak", 1.0)
        if info.get("breeding", False):
            logger.debug(f"[Seasonal] {species} en temporada de cría (mes {month}): ×{multiplier}")
        return multiplier
    else:
        return info.get("risk_multiplier_offpeak", 1.0)


def get_season_label(month: int) -> str:
    """Retorna una etiqueta de temporada para el Golfo de California."""
    if month in [12, 1, 2, 3]:
        return "winter_peak"       # Máxima diversidad de ballenas
    elif month in [4, 5]:
        return "spring_transition"
    elif month in [6, 7, 8, 9]:
        return "summer"            # Temporada de calor, menor presencia de misticetos
    elif month in [10, 11]:
        return "autumn_arrival"    # Llegada de ballenas y tiburones ballena
    return "unknown"


def get_active_species_for_month(month: int) -> list[str]:
    """
    Retorna la lista de especies con presencia pico en un mes dado.

    Útil para filtrar el análisis de riesgo a las especies en temporada.
    """
    active = []
    for sp, info in MIGRATION_WINDOWS.items():
        if month in info["peak_months"]:
            active.append(sp)
    return active


def compute_seasonal_summary(month: int) -> dict:
    """
    Genera un resumen de la situación estacional para un mes dado.

    Retorna
    -------
    dict con:
      - month         : número de mes
      - season_label  : etiqueta de temporada
      - active_species: lista de especies en pico
      - breeding_species: lista con temporada de cría activa
      - max_risk_multiplier: máximo multiplicador de riesgo del mes
    """
    active   = get_active_species_for_month(month)
    breeding = [
        sp for sp in active
        if MIGRATION_WINDOWS[sp].get("breeding", False)
    ]
    multipliers = [
        MIGRATION_WINDOWS[sp].get("risk_multiplier_peak", 1.0)
        for sp in active
    ]
    return {
        "month":                month,
        "season_label":         get_season_label(month),
        "active_species":       active,
        "breeding_species":     breeding,
        "max_risk_multiplier":  max(multipliers) if multipliers else 1.0,
    }
