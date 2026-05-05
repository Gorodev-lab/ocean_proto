"""
ocean_proto / src / pipeline / obis_client.py
==============================================
Cliente aislado para el Sistema de Información sobre Biodiversidad
Oceánica (OBIS) — endpoint público v3/occurrence.

Consulta avistamientos de megafauna marina (misticetos, odontocetos y
elasmobranquios) relevantes para el análisis de riesgo petrolero.
Devuelve siempre un DataFrame de Pandas — nunca propaga excepciones.

Paso 1 de la Guía de Integración OBIS.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Final

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ================================================================
# Constantes de configuración
# ================================================================
OBIS_BASE_URL: Final[str] = "https://api.obis.org/v3/occurrence"
OBIS_PAGE_SIZE: Final[int] = 500          # registros por página (max OBIS: 5000)
OBIS_MAX_RECORDS: Final[int] = 5000       # techo de seguridad por especie
OBIS_TIMEOUT_SECONDS: Final[int] = 30     # timeout por petición HTTP
OBIS_MAX_RETRIES: Final[int] = 3          # reintentos para errores 5xx
OBIS_BACKOFF_FACTOR: Final[float] = 1.5   # factor de espera exponencial

# Columnas que se extraen de la respuesta JSON de OBIS
_OBIS_COLUMNS: Final[list[str]] = [
    "species",
    "decimalLatitude",
    "decimalLongitude",
    "eventDate",
    "datasetName",
]

# Columnas derivadas que enriquecen el DataFrame
_ENRICHMENT_COLUMNS: Final[list[str]] = [
    "taxa_group",
    "oil_relevance",
]

# Schema completo del DataFrame de salida
OBIS_SCHEMA: Final[list[str]] = _OBIS_COLUMNS + _ENRICHMENT_COLUMNS


# ================================================================
# Catálogo de especies — WoRMS IDs
# ================================================================
@dataclass(frozen=True, slots=True)
class SpeciesRecord:
    """Registro inmutable de una especie objetivo."""
    worms_id: int
    species: str
    taxa_group: str        # Misticeto | Odontoceto | Elasmobranquio
    oil_relevance: str     # CRÍTICO | ALTO | MEDIO


# fmt: off
MEGAFAUNA_CATALOG: Final[tuple[SpeciesRecord, ...]] = (
    # ── Misticetos (ballenas barbadas) ──────────────────────────
    SpeciesRecord(137090,  "Balaenoptera musculus",      "Misticeto",       "CRÍTICO"),   # Ballena azul
    SpeciesRecord(137092,  "Balaenoptera physalus",      "Misticeto",       "CRÍTICO"),   # Rorcual común
    SpeciesRecord(137087,  "Megaptera novaeangliae",     "Misticeto",       "CRÍTICO"),   # Ballena jorobada
    SpeciesRecord(137088,  "Eschrichtius robustus",      "Misticeto",       "CRÍTICO"),   # Ballena gris
    SpeciesRecord(137091,  "Balaenoptera edeni",         "Misticeto",       "ALTO"),      # Rorcual de Bryde
    SpeciesRecord(137093,  "Balaenoptera borealis",      "Misticeto",       "ALTO"),      # Rorcual de Sei

    # ── Odontocetos (cetáceos dentados) ─────────────────────────
    SpeciesRecord(137119,  "Physeter macrocephalus",     "Odontoceto",      "CRÍTICO"),   # Cachalote
    SpeciesRecord(137094,  "Orcinus orca",               "Odontoceto",      "ALTO"),      # Orca
    SpeciesRecord(254985,  "Berardius bairdii",          "Odontoceto",      "MEDIO"),     # Zífido de Baird
    SpeciesRecord(137111,  "Tursiops truncatus",         "Odontoceto",      "MEDIO"),     # Delfín nariz de botella
    SpeciesRecord(137107,  "Delphinus delphis",          "Odontoceto",      "MEDIO"),     # Delfín común

    # ── Elasmobranquios (tiburones y rayas) ─────────────────────
    SpeciesRecord(105838,  "Rhincodon typus",            "Elasmobranquio",  "CRÍTICO"),   # Tiburón ballena
    SpeciesRecord(105851,  "Carcharodon carcharias",     "Elasmobranquio",  "ALTO"),      # Gran tiburón blanco
    SpeciesRecord(105857,  "Sphyrna mokarran",           "Elasmobranquio",  "ALTO"),      # Tiburón martillo gigante
    SpeciesRecord(105833,  "Manta birostris",            "Elasmobranquio",  "ALTO"),      # Manta gigante
    SpeciesRecord(105847,  "Isurus oxyrinchus",          "Elasmobranquio",  "MEDIO"),     # Mako
)
# fmt: on

# Lookup rápido: worms_id → SpeciesRecord
_CATALOG_BY_ID: Final[dict[int, SpeciesRecord]] = {
    sp.worms_id: sp for sp in MEGAFAUNA_CATALOG
}


# ================================================================
# Sesión HTTP con reintentos automáticos
# ================================================================
def _build_session() -> requests.Session:
    """
    Construye una sesión de ``requests`` con reintentos exponenciales
    exclusivamente para errores 5xx y fallos de conexión.

    Los errores 4xx se consideran definitivos (error del cliente) y no
    se reintentan, preservando el principio de fail-fast para datos
    incorrectos.
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=OBIS_MAX_RETRIES,
        backoff_factor=OBIS_BACKOFF_FACTOR,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ================================================================
# Función auxiliar: DataFrame vacío con schema correcto
# ================================================================
def _empty_dataframe() -> pd.DataFrame:
    """Retorna un DataFrame vacío con las columnas del schema OBIS."""
    return pd.DataFrame(columns=OBIS_SCHEMA)


# ================================================================
# Función principal
# ================================================================
def fetch_obis_megafauna(
    geometry: str | None = None,
    startdate: str | None = None,
    enddate: str | None = None,
    size: int = OBIS_PAGE_SIZE,
) -> pd.DataFrame:
    """
    Consulta la API pública de OBIS v3 para obtener registros de
    ocurrencia de megafauna marina relevante al análisis petrolero.

    Itera sobre cada especie del catálogo ``MEGAFAUNA_CATALOG``,
    extrae las columnas clave del JSON de respuesta, y enriquece
    cada registro con ``taxa_group`` y ``oil_relevance``.

    Parameters
    ----------
    geometry : str | None
        WKT del polígono de interés para filtrar espacialmente
        (e.g. ``"POLYGON((-118 22,-105 22,-105 32,-118 32,-118 22))"``).
    startdate : str | None
        Fecha ISO-8601 de inicio del rango temporal (e.g. ``"2020-01-01"``).
    enddate : str | None
        Fecha ISO-8601 de fin del rango temporal.
    size : int
        Número de registros por página (default: 500).

    Returns
    -------
    pd.DataFrame
        DataFrame con columnas: ``species``, ``decimalLatitude``,
        ``decimalLongitude``, ``eventDate``, ``datasetName``,
        ``taxa_group``, ``oil_relevance``.
        Si la API falla por completo, retorna un DataFrame vacío.
    """
    session = _build_session()
    all_records: list[dict] = []

    total_species = len(MEGAFAUNA_CATALOG)
    logger.info(
        f"[OBIS] Iniciando consulta para {total_species} especies "
        f"de megafauna marina..."
    )

    for idx, species_rec in enumerate(MEGAFAUNA_CATALOG, start=1):
        logger.info(
            f"[OBIS] ({idx}/{total_species}) Consultando "
            f"{species_rec.species} (WoRMS {species_rec.worms_id})..."
        )
        species_records = _fetch_species_occurrences(
            session=session,
            species_rec=species_rec,
            geometry=geometry,
            startdate=startdate,
            enddate=enddate,
            size=size,
        )
        all_records.extend(species_records)

    session.close()

    if not all_records:
        logger.warning(
            "[OBIS] No se obtuvieron registros de ninguna especie. "
            "Retornando DataFrame vacío."
        )
        return _empty_dataframe()

    df = pd.DataFrame(all_records, columns=OBIS_SCHEMA)

    # Limpieza defensiva de coordenadas
    df["decimalLatitude"] = pd.to_numeric(
        df["decimalLatitude"], errors="coerce"
    )
    df["decimalLongitude"] = pd.to_numeric(
        df["decimalLongitude"], errors="coerce"
    )
    df = df.dropna(subset=["decimalLatitude", "decimalLongitude"]).copy()

    logger.info(
        f"[OBIS] Consulta completa — {len(df)} registros de "
        f"{df['species'].nunique()} especies."
    )
    return df


# ================================================================
# Función interna: consulta paginada por especie
# ================================================================
def _fetch_species_occurrences(
    session: requests.Session,
    species_rec: SpeciesRecord,
    geometry: str | None,
    startdate: str | None,
    enddate: str | None,
    size: int,
) -> list[dict]:
    """
    Consulta iterativa con paginación (``after``) para una sola especie.

    Returns
    -------
    list[dict]
        Lista de diccionarios con las columnas del schema OBIS.
        Lista vacía si ocurre cualquier error.
    """
    records: list[dict] = []
    after: int | None = None      # cursor de paginación OBIS

    while len(records) < OBIS_MAX_RECORDS:
        params: dict[str, str | int] = {
            "taxonid": species_rec.worms_id,
            "size": min(size, OBIS_MAX_RECORDS - len(records)),
        }
        if geometry is not None:
            params["geometry"] = geometry
        if startdate is not None:
            params["startdate"] = startdate
        if enddate is not None:
            params["enddate"] = enddate
        if after is not None:
            params["after"] = after

        try:
            t0 = time.monotonic()
            response = session.get(
                OBIS_BASE_URL,
                params=params,
                timeout=OBIS_TIMEOUT_SECONDS,
            )
            elapsed = time.monotonic() - t0

            # ── Error 4xx: fallo del cliente → no reintentar ──
            if 400 <= response.status_code < 500:
                logger.error(
                    f"[OBIS] HTTP {response.status_code} para "
                    f"{species_rec.species} (WoRMS {species_rec.worms_id}). "
                    f"Respuesta: {response.text[:300]}"
                )
                break

            # ── Error 5xx ya fue reintentado por urllib3 ──
            if response.status_code >= 500:
                logger.error(
                    f"[OBIS] HTTP {response.status_code} persistente para "
                    f"{species_rec.species} tras {OBIS_MAX_RETRIES} "
                    f"reintentos. Abortando esta especie."
                )
                break

            data = response.json()
            results: list[dict] = data.get("results", [])

            if not results:
                logger.debug(
                    f"[OBIS] Sin más resultados para "
                    f"{species_rec.species}. Total parcial: {len(records)}."
                )
                break

            # ── Extraer y enriquecer cada registro ──
            for rec in results:
                records.append({
                    "species":           rec.get("species", species_rec.species),
                    "decimalLatitude":   rec.get("decimalLatitude"),
                    "decimalLongitude":  rec.get("decimalLongitude"),
                    "eventDate":         rec.get("eventDate"),
                    "datasetName":       rec.get("datasetName"),
                    "taxa_group":        species_rec.taxa_group,
                    "oil_relevance":     species_rec.oil_relevance,
                })

            logger.debug(
                f"[OBIS] {species_rec.species}: +{len(results)} registros "
                f"({elapsed:.1f}s) — acumulado: {len(records)}"
            )

            # ── Paginación ──
            total = data.get("total", 0)
            if len(records) >= total or len(records) >= OBIS_MAX_RECORDS:
                break

            # OBIS v3 usa cursor basado en el último ID ordinal
            # Extraer el campo de paginación del último resultado
            last_id = results[-1].get("id")
            if last_id and last_id != after:
                after = last_id
            else:
                # Sin cursor válido; salir para evitar loop infinito
                break

        except requests.exceptions.Timeout:
            logger.warning(
                f"[OBIS] Timeout ({OBIS_TIMEOUT_SECONDS}s) para "
                f"{species_rec.species}. Registros parciales: {len(records)}."
            )
            break

        except requests.exceptions.ConnectionError as exc:
            logger.error(
                f"[OBIS] Error de conexión para {species_rec.species}: "
                f"{exc}. Abortando esta especie."
            )
            break

        except requests.exceptions.RequestException as exc:
            logger.error(
                f"[OBIS] Error de red inesperado para "
                f"{species_rec.species}: {exc}."
            )
            break

        except (ValueError, KeyError) as exc:
            # JSON malformado o estructura inesperada
            logger.error(
                f"[OBIS] Error parseando respuesta para "
                f"{species_rec.species}: {exc}."
            )
            break

    if records:
        logger.info(
            f"[OBIS] {species_rec.species}: {len(records)} registros obtenidos."
        )
    return records
