"""
ocean_proto / src / pipeline / seasonal.py — GFW-ONLY
=====================================================
Criterio de estacionalidad basado en patrones de pesca del Golfo de California.

En el pipeline GFW-only, la estacionalidad se basa en los ciclos de
actividad pesquera observados en los datos de GFW, en lugar de las
ventanas migratorias biológicas de OBIS.

Fuentes de referencia:
  - GFW Fishing Effort data (público, 2012-2024)
  - Análisis estacional de esfuerzo pesquero en el Golfo de California
  - Patrones conocidos de pesquerías comerciales en BCS/GoC
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── Estacionalidad de actividad pesquera en BCS/GoC ─────────────────────────
# Basado en patrones históricos de esfuerzo pesquero de GFW.
# Valores representan el multiplicador de presión relativo al promedio anual.
#
# Meses de alta pesca en BCS/GoC:
#   - Oct-Mar: temporada de sardina, camarón de alta mar, atún
#   - Dic-Abr: temporada turística (whale watching, pesca deportiva)
#   - Jun-Sep: veda de camarón, menor actividad general
FISHING_SEASON_MODIFIERS = {
    1:  1.8,   # Enero   — pesca activa + turismo alto
    2:  1.7,   # Febrero — pesca activa + turismo pico (ballenas)
    3:  1.5,   # Marzo   — transición, pesca moderada
    4:  1.3,   # Abril   — inicio de veda de camarón en algunas zonas
    5:  1.0,   # Mayo    — actividad promedio
    6:  0.7,   # Junio   — inicio de veda general, menor presión
    7:  0.6,   # Julio   — veda activa, mínimo esfuerzo
    8:  0.6,   # Agosto  — veda activa, mínimo esfuerzo
    9:  0.8,   # Sept    — fin de veda, reinicio gradual
    10: 1.4,   # Octubre — reinicio fuerte (sardina, camarón)
    11: 1.6,   # Nov     — temporada alta de pesca industrial
    12: 1.9,   # Dic     — máxima actividad (pesca + turismo)
}


def get_fishing_season_modifier(month: int) -> float:
    """
    Retorna el multiplicador de presión estacional basado en
    patrones de pesca del Golfo de California.

    Parámetros
    ----------
    month : número de mes (1-12)

    Retorna
    -------
    float: multiplicador de presión
      - > 1.0 → temporada de alta actividad pesquera
      - < 1.0 → temporada de baja actividad (veda)
      - 1.0   → actividad promedio
    """
    return FISHING_SEASON_MODIFIERS.get(month, 1.0)


def get_season_label(month: int) -> str:
    """Retorna una etiqueta de temporada pesquera para el GoC."""
    if month in [12, 1, 2]:
        return "high_fishing_tourism"  # Máxima actividad
    elif month in [3, 4, 5]:
        return "spring_transition"
    elif month in [6, 7, 8]:
        return "summer_veda"           # Veda de camarón, menor presión
    elif month in [9, 10, 11]:
        return "autumn_restart"        # Reinicio de temporada
    return "unknown"


def get_high_pressure_months() -> list[int]:
    """
    Retorna los meses con presión antrópica por encima del promedio.
    Útil para priorizar análisis temporales.
    """
    return [m for m, v in FISHING_SEASON_MODIFIERS.items() if v > 1.0]


def compute_seasonal_summary(month: int) -> dict:
    """
    Genera un resumen de la situación estacional de presión pesquera.

    Retorna
    -------
    dict con:
      - month              : número de mes
      - season_label       : etiqueta de temporada
      - pressure_modifier  : multiplicador de presión
      - pressure_level     : HIGH / MEDIUM / LOW
      - is_veda            : si hay veda activa de camarón
    """
    modifier = get_fishing_season_modifier(month)

    if modifier >= 1.5:
        level = "HIGH"
    elif modifier >= 1.0:
        level = "MEDIUM"
    else:
        level = "LOW"

    return {
        "month":              month,
        "season_label":       get_season_label(month),
        "pressure_modifier":  modifier,
        "pressure_level":     level,
        "is_veda":            month in [6, 7, 8],
        "high_pressure_months": get_high_pressure_months(),
    }
