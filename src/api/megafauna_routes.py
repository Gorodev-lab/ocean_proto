"""
ocean_proto / src / api / megafauna_routes.py
=============================================
Router de FastAPI para los endpoints de megafauna marina (OBIS).

Expone tres endpoints GET bajo el prefijo /api/megafauna:

  GET /api/megafauna/          → Ocurrencias como GeoJSON (FeatureCollection)
  GET /api/megafauna/species   → Distribución estadística por especie
  GET /api/megafauna/hotspots  → Celdas H3 con co-ocurrencia activa (GeoJSON)

Estrategia de rendimiento:
  - El GeoJSON de puntos base se sirve directamente desde disco si existe el
    artefacto pre-computado por el ETL; en caso contrario se genera y se
    memoriza en ``_POINTS_CACHE`` (invalidable con POST /api/refresh).
  - El CSV unificado se lee una sola vez por proceso y se guarda en
    ``_UNIFIED_DF_CACHE``. La cache se invalida llamando a
    ``invalidate_megafauna_cache()`` desde el pipeline de ingesta o refresh.
  - Las operaciones de Pandas sobre CSV grandes se delegan a un thread pool
    para no bloquear el event loop de uvicorn.

Degradación segura:
  - Si el CSV unificado no existe o no tiene registros 'megafauna', todos
    los endpoints devuelven 200 con datos vacíos (no HTTP 500).
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ORJSONResponse es ~5-10x más rápido que JSONResponse (Rust vs Python).
# FastAPI expone la clase incluso sin orjson instalado, pero lanza
# AssertionError en runtime. Verificamos el módulo directamente.
try:
    import orjson as _orjson  # noqa: F401
    from fastapi.responses import ORJSONResponse as _FastResponse
except (ImportError, ModuleNotFoundError):
    _FastResponse = JSONResponse

logger = logging.getLogger(__name__)

# ── Constantes de rutas ───────────────────────────────────────────────────────
_UNIFIED_CSV      = "data/unified_ocean.csv"
_MEGAFAUNA_GEOJSON = "data/megafauna_occurrences.geojson"
_HOTSPOTS_GEOJSON  = "data/risk_hotspots.geojson"

# ── Caché de módulo (proceso-local, invalidable) ──────────────────────────────
# Se usa dict mutable como contenedor para permitir invalidación explícita,
# a diferencia de @lru_cache que es difícil de limpiar selectivamente.
_CACHE: dict = {
    "unified_df":    None,   # pd.DataFrame | None
    "points_geojson": None,  # dict (GeoJSON) | None
    "species_list":  None,   # list[dict] | None
}


def invalidate_megafauna_cache() -> None:
    """
    Invalida todas las cachés de megafauna.
    Debe llamarse tras cada ejecución del pipeline de ingesta
    (ej. al final de ``update_pipeline_task`` en routes.py).
    """
    _CACHE["unified_df"]     = None
    _CACHE["points_geojson"] = None
    _CACHE["species_list"]   = None
    logger.info("[Megafauna API] Caché invalidada.")


# ── Pydantic models ───────────────────────────────────────────────────────────

class SpeciesRecord(BaseModel):
    """Distribución estadística de una especie en el dataset OBIS."""

    species:       str           = Field(..., description="Nombre científico de la especie.")
    taxa_group:    Optional[str] = Field(None, description="Grupo taxonómico (Misticeto, Odontoceto, Elasmobranquio).")
    oil_relevance: Optional[str] = Field(None, description="Nivel de relevancia petrolera (CRÍTICO, ALTO, MEDIO).")
    count:         int           = Field(..., ge=0, description="Número de registros de ocurrencia.")
    pct_of_total:  float         = Field(..., ge=0.0, le=100.0, description="Porcentaje del total de registros OBIS.")


class SpeciesResponse(BaseModel):
    """Respuesta del endpoint /species."""

    total_records: int                = Field(..., description="Total de registros OBIS en el dataset.")
    total_species: int                = Field(..., description="Número de especies distintas.")
    species:       List[SpeciesRecord] = Field(..., description="Lista ordenada por conteo descendente.")


# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter(
    prefix="/api/megafauna",
    tags=["Megafauna"],
)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _load_megafauna_df() -> pd.DataFrame:
    """
    Carga el CSV unificado y filtra solo los registros de megafauna.

    Usa caché de módulo: solo lee disco la primera vez por proceso.
    Retorna DataFrame vacío si el archivo no existe o no hay megafauna.
    """
    if _CACHE["unified_df"] is not None:
        return _CACHE["unified_df"]

    if not os.path.exists(_UNIFIED_CSV):
        logger.info(
            f"[Megafauna API] {_UNIFIED_CSV} no encontrado. "
            "Ejecuta POST /api/refresh para generar los datos."
        )
        _CACHE["unified_df"] = pd.DataFrame()
        return _CACHE["unified_df"]

    try:
        df = pd.read_csv(
            _UNIFIED_CSV,
            usecols=lambda c: c in {
                "lat", "lon", "timestamp", "identity",
                "category", "source", "taxa_group",
                "oil_relevance", "vessel_type",
            },
            dtype={
                "category":      "category",
                "source":        "category",
                "taxa_group":    "category",
                "oil_relevance": "category",
            },
            low_memory=False,
        )

        # Filtrar solo megafauna
        meg_df = df[df["category"] == "megafauna"].copy()
        meg_df["lat"] = pd.to_numeric(meg_df["lat"], errors="coerce")
        meg_df["lon"] = pd.to_numeric(meg_df["lon"], errors="coerce")
        meg_df = meg_df.dropna(subset=["lat", "lon"])

        _CACHE["unified_df"] = meg_df
        logger.info(
            f"[Megafauna API] CSV cargado: {len(meg_df)} registros de megafauna "
            f"({meg_df['identity'].nunique() if not meg_df.empty else 0} especies)."
        )
        return _CACHE["unified_df"]

    except Exception as exc:
        logger.error(f"[Megafauna API] Error leyendo {_UNIFIED_CSV}: {exc}")
        _CACHE["unified_df"] = pd.DataFrame()
        return _CACHE["unified_df"]


def _build_points_geojson(df: pd.DataFrame) -> dict:
    """
    Construye el GeoJSON de ocurrencias desde el DataFrame filtrado.

    Construye las Features manualmente en lugar de pasar por Shapely para
    evitar la sobrecarga de ``__geo_interface__``. La serialización posterior
    la realiza ORJSONResponse (Rust), si está disponible, en lugar del encoder estándar de Python.
    """
    if df.empty:
        return {"type": "FeatureCollection", "features": []}

    features: list[dict] = []
    for row in df.itertuples(index=False, name=None):
        # Orden de columnas sigue el orden del DataFrame (asignado en _load)
        # Usar dict por posición es más rápido que getattr en itertuples nombrados
        col_map = {col: val for col, val in zip(df.columns, row)}
        lat = col_map.get("lat")
        lon = col_map.get("lon")
        if lat is None or lon is None or (isinstance(lat, float) and np.isnan(lat)):
            continue
        features.append({
            "type": "Feature",
            "geometry": {
                "type":        "Point",
                "coordinates": [float(lon), float(lat)],
            },
            "properties": {
                "species":       str(col_map.get("identity", "")),
                "taxa_group":    str(col_map.get("taxa_group", "")) or None,
                "oil_relevance": str(col_map.get("oil_relevance", "")) or None,
                "timestamp":     str(col_map.get("timestamp", "")) or None,
            },
        })

    return {"type": "FeatureCollection", "features": features}


def _build_points_geojson_vectorized(df: pd.DataFrame) -> dict:
    """
    Versión vectorizada de ``_build_points_geojson`` para DataFrames grandes.

    Construye las Features usando operaciones de Pandas sobre columnas en lugar
    de iteración fila por fila, reduciendo el overhead del intérprete Python.
    """
    if df.empty:
        return {"type": "FeatureCollection", "features": []}

    # Normalizar strings para columnas opcionales
    taxa      = df["taxa_group"].astype(str).where(df["taxa_group"].notna(), None)
    oil_rel   = df["oil_relevance"].astype(str).where(df["oil_relevance"].notna(), None)
    timestamp = df["timestamp"].astype(str).where(df["timestamp"].notna(), None)

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "species":       species,
                "taxa_group":    tg,
                "oil_relevance": oil,
                "timestamp":     ts,
            },
        }
        for lat, lon, species, tg, oil, ts in zip(
            df["lat"].tolist(),
            df["lon"].tolist(),
            df["identity"].tolist(),
            taxa.tolist(),
            oil_rel.tolist(),
            timestamp.tolist(),
        )
    ]
    return {"type": "FeatureCollection", "features": features}


def _get_or_build_points_geojson() -> dict:
    """
    Obtiene el GeoJSON de puntos desde caché o lo construye.

    Prioridad:
      1. Caché en memoria (``_CACHE['points_geojson']``).
      2. Archivo pre-computado en disco (``_MEGAFAUNA_GEOJSON``).
      3. Construcción desde el CSV en memoria.
    """
    if _CACHE["points_geojson"] is not None:
        return _CACHE["points_geojson"]

    # Intentar leer el artefacto pre-computado del ETL
    if os.path.exists(_MEGAFAUNA_GEOJSON):
        try:
            with open(_MEGAFAUNA_GEOJSON, "r", encoding="utf-8") as fh:
                geojson = json.load(fh)
            _CACHE["points_geojson"] = geojson
            logger.info(
                f"[Megafauna API] GeoJSON servido desde disco "
                f"({len(geojson.get('features', []))} features)."
            )
            return _CACHE["points_geojson"]
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning(f"[Megafauna API] Error leyendo GeoJSON de disco: {exc}. Reconstruyendo.")

    # Construir desde el CSV en memoria
    df = _load_megafauna_df()
    geojson = _build_points_geojson_vectorized(df)

    # Persistir en disco para requests futuros (ETL-once, serve-many)
    if geojson["features"]:
        try:
            os.makedirs("data", exist_ok=True)
            with open(_MEGAFAUNA_GEOJSON, "w", encoding="utf-8") as fh:
                json.dump(geojson, fh, ensure_ascii=False, separators=(",", ":"))
            logger.info(
                f"[Megafauna API] GeoJSON persistido en disco "
                f"({len(geojson['features'])} features)."
            )
        except IOError as exc:
            logger.warning(f"[Megafauna API] No se pudo persistir GeoJSON: {exc}")

    _CACHE["points_geojson"] = geojson
    return _CACHE["points_geojson"]


def _build_species_stats(df: pd.DataFrame) -> SpeciesResponse:
    """
    Calcula la distribución estadística de species desde el DataFrame.
    Devuelve SpeciesResponse con lista ordenada por conteo descendente.
    """
    if df.empty:
        return SpeciesResponse(total_records=0, total_species=0, species=[])

    total = len(df)

    # Agrupación vectorizada: sin bucles Python por especie
    agg = (
        df.groupby("identity", observed=True)
        .agg(
            count=("identity", "size"),
            taxa_group=("taxa_group", "first"),
            oil_relevance=("oil_relevance", "first"),
        )
        .reset_index()
        .sort_values("count", ascending=False)
    )

    agg["pct_of_total"] = (agg["count"] / total * 100.0).round(2)

    species_list = [
        SpeciesRecord(
            species=str(row["identity"]),
            taxa_group=str(row["taxa_group"]) if pd.notna(row["taxa_group"]) else None,
            oil_relevance=str(row["oil_relevance"]) if pd.notna(row["oil_relevance"]) else None,
            count=int(row["count"]),
            pct_of_total=float(row["pct_of_total"]),
        )
        for _, row in agg.iterrows()
    ]

    return SpeciesResponse(
        total_records=total,
        total_species=len(species_list),
        species=species_list,
    )


def _build_cooccurrence_hotspots() -> dict:
    """
    Lee el GeoJSON de hotspots del pipeline y filtra celdas donde
    ``score_cooccurrence > 0``, ordenadas de mayor a menor.

    Retorna un GeoJSON válido (FeatureCollection).
    """
    if not os.path.exists(_HOTSPOTS_GEOJSON):
        return {"type": "FeatureCollection", "features": []}

    try:
        with open(_HOTSPOTS_GEOJSON, "r", encoding="utf-8") as fh:
            hotspots = json.load(fh)
    except (json.JSONDecodeError, IOError) as exc:
        logger.error(f"[Megafauna API] Error leyendo hotspots: {exc}")
        return {"type": "FeatureCollection", "features": []}

    # Filtrar y ordenar — operación sobre lista, no GeoDataFrame completo
    features_with_cooc = [
        feat for feat in hotspots.get("features", [])
        if float(feat.get("properties", {}).get("score_cooccurrence", 0.0) or 0.0) > 0.0
    ]

    features_with_cooc.sort(
        key=lambda f: float(f.get("properties", {}).get("score_cooccurrence", 0.0) or 0.0),
        reverse=True,
    )

    logger.info(
        f"[Megafauna API] Hotspots con co-ocurrencia: "
        f"{len(features_with_cooc)} / {len(hotspots.get('features', []))} celdas."
    )
    return {"type": "FeatureCollection", "features": features_with_cooc}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/",
    summary="Ocurrencias de megafauna (GeoJSON)",
    response_description="FeatureCollection con todos los avistamientos OBIS.",
)
async def get_megafauna_occurrences() -> JSONResponse:
    """
    Retorna todos los registros de ocurrencia de megafauna marina como
    GeoJSON ``FeatureCollection``.

    Cada Feature es un punto con propiedades:
    - ``species``       : nombre científico
    - ``taxa_group``    : Misticeto | Odontoceto | Elasmobranquio
    - ``oil_relevance`` : CRÍTICO | ALTO | MEDIO
    - ``timestamp``     : fecha del avistamiento (ISO-8601)

    **Rendimiento**: el GeoJSON se construye una vez y se almacena en disco
    y en memoria. Las peticiones subsecuentes se sirven desde caché sin
    tocar Pandas ni el sistema de archivos.
    """
    try:
        # Delegar trabajo de disco/CPU al thread pool para no bloquear el event loop
        geojson = await run_in_threadpool(_get_or_build_points_geojson)
        return _FastResponse(content=geojson)
    except Exception as exc:
        logger.error(f"[GET /api/megafauna/] Error: {exc}", exc_info=True)
        return _FastResponse(
            content={"type": "FeatureCollection", "features": []},
        )


@router.get(
    "/species",
    summary="Distribución estadística por especie",
    response_model=SpeciesResponse,
    response_description="Lista de especies con conteos y metadatos taxonómicos.",
)
async def get_species_distribution() -> SpeciesResponse:
    """
    Retorna la distribución estadística de avistamientos por especie.

    Incluye: nombre científico, grupo taxonómico, nivel de relevancia
    petrolera, conteo de registros y porcentaje del total OBIS.

    La lista viene ordenada de mayor a menor número de registros.
    Si OBIS no aportó datos en el último ETL, retorna listas vacías (HTTP 200).
    """
    try:
        # Usar caché si ya fue calculado
        if _CACHE["species_list"] is not None:
            return _CACHE["species_list"]

        df = await run_in_threadpool(_load_megafauna_df)
        result = await run_in_threadpool(_build_species_stats, df)

        # Memorizar solo si hay datos reales (evitar cachear estado vacío)
        if result.total_records > 0:
            _CACHE["species_list"] = result

        return result

    except Exception as exc:
        logger.error(f"[GET /api/megafauna/species] Error: {exc}", exc_info=True)
        return SpeciesResponse(total_records=0, total_species=0, species=[])


@router.get(
    "/hotspots",
    summary="Hotspots de co-ocurrencia megafauna × embarcaciones",
    response_description="FeatureCollection con celdas H3 de alto riesgo (score_cooccurrence > 0).",
)
async def get_cooccurrence_hotspots() -> JSONResponse:
    """
    Retorna las celdas H3 donde existe co-ocurrencia confirmada entre
    megafauna marina (OBIS) y embarcaciones (GFW), ordenadas de mayor a
    menor ``score_cooccurrence``.

    Cada Feature es un polígono H3 con propiedades heredadas del pipeline IPA:
    ``h3_index``, ``score_cooccurrence``, ``vessel_count``, ``megafauna_count``,
    ``ipa_100``, ``ipa_level``.

    Si el pipeline aún no ha corrido o OBIS no aportó datos, retorna una
    ``FeatureCollection`` vacía con HTTP 200.
    """
    try:
        geojson = await run_in_threadpool(_build_cooccurrence_hotspots)
        return _FastResponse(content=geojson)
    except Exception as exc:
        logger.error(f"[GET /api/megafauna/hotspots] Error: {exc}", exc_info=True)
        return _FastResponse(
            content={"type": "FeatureCollection", "features": []},
        )
