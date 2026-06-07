import os
import json
import time
import logging
from dotenv import load_dotenv
from src.pipeline._resilience import http_get, http_post

load_dotenv()
logger = logging.getLogger(__name__)

GFW_BASE_URL    = "https://gateway.api.globalfishingwatch.org"
GFW_API_URL     = f"{GFW_BASE_URL}/v3/events"
# La infraestructura offshore se descarga vía el Data Download API de GFW:
#   POST /v3/datasets/{id}/download  → job_id
#   GET  /v3/download/{job_id}       → poll hasta que el archivo esté listo
GFW_INFRA_DATASET   = "public-fixed-infrastructure-filtered:latest"
GFW_DOWNLOAD_URL    = f"{GFW_BASE_URL}/v3/datasets/{GFW_INFRA_DATASET}/download"
GFW_DOWNLOAD_POLL   = f"{GFW_BASE_URL}/v3/download"

CACHE_FILE              = "data/gfw_live_cache.json"
OIL_PLATFORMS_CACHE     = "data/gfw_oil_platforms_cache.json"
CACHE_EXPIRY_SECONDS    = 7200   # 2 horas  (vessel events)
PLATFORMS_CACHE_EXPIRY  = 28800  # 8 horas  (infraestructura cambia poco)

def fetch_live_vessels(bbox: tuple) -> list:
    """
    Realiza una consulta a la API de GFW para buscar embarcaciones,
    manejando paginación y empleando un caché local de 2 horas.
    bbox: (min_lon, min_lat, max_lon, max_lat)
    """
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    
    # 1. Comprobar caché local
    if os.path.exists(CACHE_FILE):
        file_age = time.time() - os.path.getmtime(CACHE_FILE)
        if file_age < CACHE_EXPIRY_SECONDS:
            try:
                with open(CACHE_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass  # Caché corrupto, continuar a la red

    # 2. Configurar Autenticación
    token = os.environ.get("GFW_API_TOKEN")
    if not token:
        logger.warning("No se encontró el token de GFW (GFW_API_TOKEN) en el entorno.")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    min_lon, min_lat, max_lon, max_lat = bbox
    # Construcción segura usando v2/events
    params = {
        "datasets": "public-global-fishing-events:latest",
        "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "limit": 50,  
        "offset": 0
    }

    all_records = []
    
    try:
        while True:
            data = http_get(GFW_API_URL, params=params, token=token, timeout=20)
            if data is None:
                break  # _resilience ya logueó el error

            entries = data.get('entries', []) if isinstance(data, dict) else data
            if not entries:
                break
            all_records.extend(entries)

            if isinstance(data, dict) and data.get('next') and params['offset'] < 200:
                params['offset'] += params['limit']
            else:
                break

        with open(CACHE_FILE, 'w') as f:
            json.dump(all_records, f)
        return all_records

    except Exception as e:
        logger.error("Error inesperado en fetch_live_vessels: %s", e)
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        return []

def search_passenger_and_tanker_vessels() -> list:
    """
    Busca Megacruceros y Tankers en el dataset de identidad GFW.
    Retorna lista de entradas o [] si falla.
    """
    token = os.environ.get("GFW_API_TOKEN")
    if not token:
        logger.warning("[Vessel Search] GFW_API_TOKEN no disponible.")
        return []

    url = "https://gateway.api.globalfishingwatch.org/v3/vessels/search"
    params = {
        "datasets": "public-global-vessel-identity:latest",
        "query":    "vesselClass:passenger OR vesselClass:tanker",
        "limit":    50,
    }
    data = http_get(url, params=params, token=token, timeout=20)
    if not data:
        return []
    return data.get("entries", [])


# ================================================================
# FUENTE 3: Plataformas O&G offshore
# ================================================================
# GFW Infrastructure solo sirve tiles MVT (sin download API REST).
# Usamos BOEM ArcGIS REST como fuente primaria (US waters) + fallback
# a CSV manual del portal GFW (data/gfw_oil_platforms_manual.csv).
#
# BOEM ArcGIS REST API (MarineCadastre.gov):
#   https://services2.arcgis.com/C8EMgrsFjeWyfcqP/arcgis/rest/services/
#   Oilgas_Facilities_in_the_US/FeatureServer/0/query
#
BOEM_API_URL = (
    "https://services2.arcgis.com/C8EMgrsFjeWyfcqP/arcgis/rest/services"
    "/Oilgas_Facilities_in_the_US/FeatureServer/0/query"
)

# CSV pre-descargado manualmente desde el portal GFW
GFW_MANUAL_CSV = "data/gfw_fixed_infrastructure_oil.csv"


def fetch_oil_platforms(bbox: tuple | None = None) -> list[dict]:
    """
    Descarga plataformas offshore de O&G desde BOEM ArcGIS REST API.

    Fuente primaria : BOEM MarineCadastre (aguas federales de EUA)
    Fuente secundaria: CSV pre-descargado manualmente del portal GFW
                       (colocar en data/gfw_fixed_infrastructure_oil.csv)

    Parámetros
    ----------
    bbox : (min_lon, min_lat, max_lon, max_lat) | None
        Filtro geográfico.
    """
    os.makedirs("data", exist_ok=True)

    # 1. Caché local (8 h)
    if os.path.exists(OIL_PLATFORMS_CACHE):
        age = time.time() - os.path.getmtime(OIL_PLATFORMS_CACHE)
        if age < PLATFORMS_CACHE_EXPIRY:
            try:
                with open(OIL_PLATFORMS_CACHE, "r") as f:
                    cached = json.load(f)
                logger.info(
                    f"[Oil Platforms] Usando caché local ({len(cached)} plataformas)"
                )
                return cached
            except json.JSONDecodeError:
                pass

    all_platforms: list[dict] = []

    # 2. Fuente primaria: BOEM ArcGIS REST
    boem_platforms = _fetch_boem_platforms(bbox)
    if boem_platforms:
        all_platforms.extend(boem_platforms)

    # 3. Fuente secundaria: CSV manual del portal GFW
    gfw_platforms = _load_gfw_manual_csv(bbox)
    if gfw_platforms:
        all_platforms.extend(gfw_platforms)

    if not all_platforms:
        logger.warning(
            "[Oil Platforms] Sin datos de plataformas. "
            "Si deseas datos GFW, descarga manualmente desde: "
            "https://globalfishingwatch.org/data-download/datasets/public-fixed-infrastructure "
            "y coloca el CSV en data/gfw_fixed_infrastructure_oil.csv"
        )
        return _load_platforms_cache_fallback()

    # 4. Guardar en caché
    with open(OIL_PLATFORMS_CACHE, "w") as f:
        json.dump(all_platforms, f, indent=2)
    logger.info(
        f"[Oil Platforms] {len(all_platforms)} plataformas O&G guardadas en caché "
        f"(BOEM: {len(boem_platforms)}, GFW manual: {len(gfw_platforms)})"
    )
    return all_platforms


def _fetch_boem_platforms(bbox: tuple | None) -> list[dict]:
    """
    Descarga plataformas O&G de BOEM via opendata.arcgis.com GeoJSON endpoint.

    Dataset: OCS Oil and Natural Gas Platforms – Gulf of Mexico Region
    ID: 5f96bdc123d34a9cb742d7137bacff62_0
    Fuente: NOAA/MarineCadastre a través del ArcGIS Hub
    """
    # ID verificado: 'OCS Oil and Natural Gas Platforms - Gulf of Mexico Region'
    DATASET_ID = "5f96bdc123d34a9cb742d7137bacff62_0"
    url = (
        f"https://opendata.arcgis.com/api/v3/datasets/{DATASET_ID}/downloads/data"
    )
    params: dict = {
        "format":       "geojson",
        "spatialRefId": "4326",
        "where":        "1=1",
    }

    all_features: list[dict] = []
    logger.info("[BOEM] Descargando plataformas O&G del Gulf of Mexico (GeoJSON)...")
    data = http_get(url, params=params, timeout=60)
    if not data:
        return []

    features = data.get("features", [])
    logger.info("[BOEM] %d plataformas en GeoJSON crudo.", len(features))

    for feat in features:
        props = feat.get("properties", {})
        geom  = feat.get("geometry", {})
        coords = geom.get("coordinates", []) if geom else []
        if not coords or len(coords) < 2:
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            continue

        if bbox:
            min_lon, min_lat, max_lon, max_lat = bbox
            if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
                continue

        all_features.append({
            "platform_id":     str(props.get("OBJECTID", "") or props.get("objectid", "")),
            "lat":             lat,
            "lon":             lon,
            "category":        "OIL",
            "label":           str(props.get("STRUCT_TYPE", "") or props.get("struct_type", "")),
            "sub_category":    "BOEM_GOM",
            "first_timestamp": str(props.get("INSTALL_DATE", "") or ""),
            "last_timestamp":  str(props.get("REMOVAL_DATE", "") or ""),
            "source":          "BOEM_arcgis",
        })

    logger.info("[BOEM] %d plataformas tras filtro bbox.", len(all_features))
    return all_features



def _load_gfw_manual_csv(bbox: tuple | None) -> list[dict]:
    """
    Carga el CSV del portal GFW si fue descargado manualmente.
    El archivo debe estar en data/gfw_fixed_infrastructure_oil.csv
    con columnas: lon, lat, label, label_confidence, structure_id,
                  structure_start_date, structure_end_date
    """
    import csv
    if not os.path.exists(GFW_MANUAL_CSV):
        return []

    platforms: list[dict] = []
    with open(GFW_MANUAL_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row.get("lat", "") or row.get("latitude", ""))
                lon = float(row.get("lon", "") or row.get("longitude", ""))
            except (ValueError, TypeError):
                continue
            label = row.get("label", "").lower()
            if label not in ("oil", ""):  # filtrar solo oil
                continue
            if bbox:
                min_lon, min_lat, max_lon, max_lat = bbox
                if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
                    continue
            platforms.append({
                "platform_id":     row.get("structure_id", ""),
                "lat":             lat,
                "lon":             lon,
                "category":        "OIL",
                "label":           row.get("label", "oil"),
                "sub_category":    row.get("label_confidence", ""),
                "first_timestamp": row.get("structure_start_date", ""),
                "last_timestamp":  row.get("structure_end_date", ""),
                "source":          "GFW_infrastructure",
            })
    logger.info(f"[GFW Manual CSV] {len(platforms)} plataformas cargadas.")
    return platforms


def _load_platforms_cache_fallback() -> list[dict]:
    """Intenta cargar la caché aunque esté expirada, como último recurso."""
    if os.path.exists(OIL_PLATFORMS_CACHE):
        try:
            with open(OIL_PLATFORMS_CACHE, "r") as f:
                stale = json.load(f)
            logger.warning(
                f"[GFW Infra] Usando caché expirada como fallback "
                f"({len(stale)} plataformas)."
            )
            return stale
        except json.JSONDecodeError:
            pass
    logger.warning("[GFW Infra] No hay caché disponible. Retornando lista vacía.")
    return []


# ================================================================
# FUENTE 4: GFW — Buques de apoyo O&G (Offshore Supply Vessels)
# ================================================================
SUPPORT_VESSELS_CACHE    = "data/gfw_support_vessels_cache.json"
SUPPORT_VESSELS_EXPIRY   = 14400   # 4 horas

def fetch_support_vessels(
    bbox: tuple | None = None,
    flags: list[str] | None = None,
    limit: int = 200,
) -> list[dict]:
    """
    Busca buques de apoyo offshore (OSVs, PSVs, AHTS) en la zona de interés.
    Dataset: public-global-support-vessels:latest
    Acciones disponibles: basic-search, advanced-search, read, vessel-insights

    Parámetros
    ----------
    bbox  : (min_lon, min_lat, max_lon, max_lat) | None
    flags : lista de códigos ISO3 de bandera, ej. ['MEX', 'PAN', 'BHS']
    limit : máximo de resultados
    """
    os.makedirs("data", exist_ok=True)

    # Caché local (4 h)
    if os.path.exists(SUPPORT_VESSELS_CACHE):
        age = time.time() - os.path.getmtime(SUPPORT_VESSELS_CACHE)
        if age < SUPPORT_VESSELS_EXPIRY:
            try:
                with open(SUPPORT_VESSELS_CACHE, "r") as f:
                    cached = json.load(f)
                logger.info(
                    f"[Support Vessels] Usando caché ({len(cached)} buques)"
                )
                return cached
            except json.JSONDecodeError:
                pass

    token = os.environ.get("GFW_API_TOKEN")
    if not token:
        logger.warning("[Support Vessels] GFW_API_TOKEN no disponible.")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    # Construir query de búsqueda
    where_clauses: list[str] = []
    if flags:
        flag_list = " OR ".join(f'flag="{f}"' for f in flags)
        where_clauses.append(f"({flag_list})")

    params: dict = {
        "datasets": "public-global-support-vessels:latest",
        "limit":    min(limit, 50),   # GFW max por página
        "offset":   0,
    }
    if where_clauses:
        params["where"] = " AND ".join(where_clauses)

    all_vessels: list[dict] = []
    url = f"{GFW_BASE_URL}/v3/vessels/search"

    try:
        while len(all_vessels) < limit:
            logger.info(
                f"[Support Vessels] Buscando OSVs "
                f"(offset={params['offset']})..."
            )
            data = http_get(url, params=params, token=token, timeout=20)
            if data is None:
                break

            entries = data.get("entries", [])
            if not entries:
                break

            for e in entries:
                # Extraer coordenadas del último registro de posición
                lat = e.get("lat") or e.get("lastPositionLat")
                lon = e.get("lon") or e.get("lastPositionLon")

                # Filtro bbox si se provee
                if bbox and lat is not None and lon is not None:
                    min_lon, min_lat, max_lon, max_lat = bbox
                    try:
                        if not (min_lat <= float(lat) <= max_lat and
                                min_lon <= float(lon) <= max_lon):
                            continue
                    except (TypeError, ValueError):
                        pass

                all_vessels.append({
                    "vessel_id":   e.get("id", ""),
                    "mmsi":        e.get("ssvid", ""),
                    "imo":         e.get("imo", ""),
                    "shipname":    e.get("shipname", ""),
                    "flag":        e.get("flag", ""),
                    "vessel_type": e.get("vesselType", "support"),
                    "gear_type":   e.get("geartypes", [""])[0]
                                   if isinstance(e.get("geartypes"), list)
                                   else e.get("geartypes", ""),
                    "lat":         lat,
                    "lon":         lon,
                    "length_m":    e.get("lengthM", None),
                    "tonnage_gt":  e.get("tonnageGt", None),
                    "source":      "GFW_support_vessels",
                })

            total = data.get("total", 0)
            next_offset = params["offset"] + params["limit"]
            if next_offset < total and next_offset < limit:
                params["offset"] = next_offset
            else:
                break

        # Guardar en caché
        with open(SUPPORT_VESSELS_CACHE, "w") as f:
            json.dump(all_vessels, f, indent=2)
        logger.info("[Support Vessels] %d buques OSV encontrados.", len(all_vessels))

    except Exception as exc:
        logger.error("[Support Vessels] Error inesperado: %s", exc)

    return all_vessels


# ================================================================
# FUENTE 5: GFW — AIS Gap Events (apagones de transpondedor)
# ================================================================
GAP_EVENTS_CACHE   = "data/gfw_gap_events_cache.json"
GAP_EVENTS_EXPIRY  = 7200   # 2 horas

def fetch_gap_events(
    bbox: tuple | None = None,
    start_date: str = "2023-01-01",
    end_date:   str = "2023-12-31",
    min_gap_hours: float = 6.0,
    limit: int = 500,
) -> list[dict]:
    """
    Descarga eventos de AIS gap (apagones de transpondedor) en el área de interés.
    Dataset: public-global-gaps-events:latest

    Los gaps son críticos para el análisis O&G: buques que apagan el AIS
    cerca de áreas de ballenas pueden estar realizando operaciones ilegales
    (vertidos, tráfico ilícito, sísmica no reportada).

    Parámetros
    ----------
    bbox          : (min_lon, min_lat, max_lon, max_lat)
    start_date    : fecha inicio ISO-8601
    end_date      : fecha fin   ISO-8601
    min_gap_hours : duración mínima del gap para incluirlo (horas)
    limit         : máximo de eventos
    """
    os.makedirs("data", exist_ok=True)

    # Caché (2 h)
    if os.path.exists(GAP_EVENTS_CACHE):
        age = time.time() - os.path.getmtime(GAP_EVENTS_CACHE)
        if age < GAP_EVENTS_EXPIRY:
            try:
                with open(GAP_EVENTS_CACHE, "r") as f:
                    cached = json.load(f)
                logger.info(
                    f"[GAP Events] Usando caché ({len(cached)} eventos)"
                )
                return cached
            except json.JSONDecodeError:
                pass

    token = os.environ.get("GFW_API_TOKEN")
    if not token:
        logger.warning("[GAP Events] GFW_API_TOKEN no disponible.")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    params: dict = {
        "datasets":   "public-global-gaps-events:latest",
        "limit":      min(limit, 50),
        "offset":     0,
        "start-date": start_date,
        "end-date":   end_date,
    }
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        params["bbox"] = f"{min_lon},{min_lat},{max_lon},{max_lat}"

    all_gaps: list[dict] = []
    url = f"{GFW_BASE_URL}/v3/events"

    try:
        while len(all_gaps) < limit:
            logger.info(
                f"[GAP Events] Consultando gaps AIS "
                f"(offset={params['offset']}, {start_date}→{end_date})..."
            )
            data = http_get(url, params=params, token=token, timeout=25)
            if data is None:
                break

            entries = data.get("entries", [])
            if not entries:
                break

            for ev in entries:
                # Calcular duración del gap en horas
                start = ev.get("start", "")
                end_t = ev.get("end", "")
                gap_hours = 0.0
                try:
                    from datetime import datetime
                    fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
                    t0 = datetime.strptime(start, fmt)
                    t1 = datetime.strptime(end_t, fmt)
                    gap_hours = (t1 - t0).total_seconds() / 3600.0
                except Exception:
                    pass

                # Filtrar por duración mínima
                if gap_hours < min_gap_hours:
                    continue

                pos = ev.get("position", {}) or {}
                lat = pos.get("lat")
                lon = pos.get("lon")

                vessel = ev.get("vessel", {}) or {}

                all_gaps.append({
                    "gap_id":      ev.get("id", ""),
                    "vessel_id":   vessel.get("id", ""),
                    "mmsi":        vessel.get("ssvid", ""),
                    "shipname":    vessel.get("name", ""),
                    "flag":        vessel.get("flag", ""),
                    "lat":         lat,
                    "lon":         lon,
                    "start":       start,
                    "end":         end_t,
                    "gap_hours":   round(gap_hours, 2),
                    "vessel_type": "unknown",
                    "source":      "GFW_gaps",
                })

            total = data.get("total", 0)
            next_offset = params["offset"] + params["limit"]
            if next_offset < total and next_offset < limit:
                params["offset"] = next_offset
            else:
                break

        # Guardar en caché
        with open(GAP_EVENTS_CACHE, "w") as f:
            json.dump(all_gaps, f, indent=2)
        logger.info(
            f"[GAP Events] {len(all_gaps)} gaps AIS ≥ {min_gap_hours}h encontrados."
        )

    except Exception as exc:
        import logging as _lg; _lg.getLogger(__name__).error("Pipeline error: %s", exc)

    return all_gaps


# ================================================================
# FUENTE 6: GFW — 4Wings Presence Heatmap (tráfico naval por hex)
# ================================================================
HEATMAP_CACHE  = "data/gfw_presence_heatmap_cache.json"
HEATMAP_EXPIRY = 21600   # 6 horas

def fetch_presence_heatmap(
    polygon_coords: list[list[float]] | None = None,
    eez_id: int | None = 8383,              # México EEZ por defecto
    start_date: str = "2023-01-01",
    end_date:   str = "2023-12-31",
    group_by: str = "gearType",
    spatial_resolution: str = "low",
    temporal_resolution: str = "yearly",
) -> list[dict]:
    """
    Genera un heatmap de presencia de buques usando el endpoint 4Wings.
    Dataset: public-global-presence:latest
    Acción: report

    El resultado es una lista de celdas con horas de presencia por grupo
    (bandera, tipo de equipo, etc.). Se usa para cuantificar el tráfico
    naval en zonas de hábitat de ballenas.

    Parámetros
    ----------
    polygon_coords      : coordenadas [[lon,lat],...] de un polígono custom
                          Si None, usa el EEZ especificado en eez_id.
    eez_id             : ID de EEZ en el dataset public-eez-areas:v12
                          México = 8383, EEZ internacional = usa polygon.
    start_date / end_date : rango máximo 366 días
    group_by            : 'gearType' | 'flag' | 'vesselId'
    spatial_resolution  : 'low' | 'medium' | 'high'
    temporal_resolution : 'daily' | 'monthly' | 'yearly'
    """
    os.makedirs("data", exist_ok=True)

    # Caché (6 h)
    if os.path.exists(HEATMAP_CACHE):
        age = time.time() - os.path.getmtime(HEATMAP_CACHE)
        if age < HEATMAP_EXPIRY:
            try:
                with open(HEATMAP_CACHE, "r") as f:
                    cached = json.load(f)
                logger.info(
                    f"[4Wings Heatmap] Usando caché ({len(cached)} celdas)"
                )
                return cached
            except json.JSONDecodeError:
                pass

    token = os.environ.get("GFW_API_TOKEN")
    if not token:
        logger.warning("[4Wings Heatmap] GFW_API_TOKEN no disponible.")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    query_params: dict = {
        "datasets[0]":         "public-global-presence:latest",
        "start-date":          start_date,
        "end-date":            end_date,
        "spatial-resolution":  spatial_resolution,
        "temporal-resolution": temporal_resolution,
        "group-by":            group_by,
    }

    # Región: polígono custom o EEZ
    if polygon_coords:
        body = {
            "region": {
                "type": "Feature",
                "geometry": {
                    "type":        "Polygon",
                    "coordinates": [polygon_coords],
                },
            }
        }
    else:
        body = {
            "region": {
                "dataset": "public-eez-areas:v12",
                "id":      eez_id,
            }
        }

    url = f"{GFW_BASE_URL}/v3/4wings/report"
    all_cells: list[dict] = []

    try:
        logger.info(
            f"[4Wings Heatmap] Solicitando presencia "
            f"({start_date} → {end_date}, group={group_by})..."
        )
        raw = http_post(url, json=body, params=query_params, token=token, timeout=60)
        if raw is None:
            return all_cells

        # La respuesta puede ser lista de entradas o dict con entries
        entries = raw if isinstance(raw, list) else raw.get("entries", [raw])

        for cell in entries:
            if not isinstance(cell, dict):
                continue
            all_cells.append({
                "h3_index":       cell.get("h3", cell.get("cellId", "")),
                "lat":            cell.get("lat"),
                "lon":            cell.get("lon"),
                "hours":          cell.get("hours", 0),
                "group":          cell.get("group", ""),
                "period":         cell.get("period", ""),
                "temporal_slice": cell.get("temporalSlice", ""),
                "source":         "GFW_4wings_presence",
            })

        # Guardar en caché
        with open(HEATMAP_CACHE, "w") as f:
            json.dump(all_cells, f, indent=2)
        logger.info(
            f"[4Wings Heatmap] {len(all_cells)} celdas de presencia obtenidas."
        )

    except Exception as exc:
        import logging as _lg; _lg.getLogger(__name__).error("Pipeline error: %s", exc)

    return all_cells


# ================================================================
# FUENTE 7: GFW — Encounter Events (transbordo en mar)
# ================================================================
ENCOUNTER_CACHE  = "data/gfw_encounters_cache.json"
ENCOUNTER_EXPIRY = 7200   # 2 horas

def fetch_encounter_events(
    bbox: tuple | None = None,
    start_date: str = "2023-01-01",
    end_date:   str = "2023-12-31",
    limit: int = 500,
) -> list[dict]:
    """
    Descarga eventos de encuentro entre embarcaciones (transbordo potencial).
    Dataset: public-global-encounters-events:latest

    Los encounters indican posible transbordo de carga/pesca en alta mar,
    una señal de actividad no regulada que incrementa la presión antrópica.
    """
    os.makedirs("data", exist_ok=True)

    if os.path.exists(ENCOUNTER_CACHE):
        age = time.time() - os.path.getmtime(ENCOUNTER_CACHE)
        if age < ENCOUNTER_EXPIRY:
            try:
                with open(ENCOUNTER_CACHE, "r") as f:
                    cached = json.load(f)
                logger.info(f"[Encounters] Usando caché ({len(cached)} eventos)")
                return cached
            except json.JSONDecodeError:
                pass

    token = os.environ.get("GFW_API_TOKEN")
    if not token:
        logger.warning("[Encounters] GFW_API_TOKEN no disponible.")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    params: dict = {
        "datasets":   "public-global-encounters-events:latest",
        "limit":      min(limit, 50),
        "offset":     0,
        "start-date": start_date,
        "end-date":   end_date,
    }
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        params["bbox"] = f"{min_lon},{min_lat},{max_lon},{max_lat}"

    all_encounters: list[dict] = []
    url = f"{GFW_BASE_URL}/v3/events"

    try:
        while len(all_encounters) < limit:
            logger.info(
                f"[Encounters] Consultando encounters "
                f"(offset={params['offset']})..."
            )
            data = http_get(url, params=params, token=token, timeout=25)
            if data is None:
                break

            entries = data.get("entries", [])
            if not entries:
                break

            for ev in entries:
                pos = ev.get("position", {}) or {}
                lat = pos.get("lat")
                lon = pos.get("lon")
                vessel = ev.get("vessel", {}) or {}

                # Duración del encuentro
                start = ev.get("start", "")
                end_t = ev.get("end", "")
                duration_h = 0.0
                try:
                    from datetime import datetime
                    fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
                    t0 = datetime.strptime(start, fmt)
                    t1 = datetime.strptime(end_t, fmt)
                    duration_h = (t1 - t0).total_seconds() / 3600.0
                except Exception:
                    pass

                all_encounters.append({
                    "encounter_id": ev.get("id", ""),
                    "vessel_id":    vessel.get("id", ""),
                    "mmsi":         vessel.get("ssvid", ""),
                    "shipname":     vessel.get("name", ""),
                    "flag":         vessel.get("flag", ""),
                    "lat":          lat,
                    "lon":          lon,
                    "start":        start,
                    "end":          end_t,
                    "duration_h":   round(duration_h, 2),
                    "source":       "GFW_encounters",
                })

            total = data.get("total", 0)
            next_offset = params["offset"] + params["limit"]
            if next_offset < total and next_offset < limit:
                params["offset"] = next_offset
            else:
                break

        with open(ENCOUNTER_CACHE, "w") as f:
            json.dump(all_encounters, f, indent=2)
        logger.info(f"[Encounters] {len(all_encounters)} encuentros encontrados.")

    except Exception as exc:
        import logging as _lg; _lg.getLogger(__name__).error("Pipeline error: %s", exc)

    return all_encounters


# ================================================================
# FUENTE 8: GFW — Loitering Events (merodeo en zona)
# ================================================================
LOITERING_CACHE  = "data/gfw_loitering_cache.json"
LOITERING_EXPIRY = 7200   # 2 horas

def fetch_loitering_events(
    bbox: tuple | None = None,
    start_date: str = "2023-01-01",
    end_date:   str = "2023-12-31",
    limit: int = 500,
) -> list[dict]:
    """
    Descarga eventos de loitering (merodeo) en el área de interés.
    Dataset: public-global-loitering-events:latest

    El loitering indica buques que permanecen en una zona sin actividad
    de pesca clara — puede indicar transbordo preparatorio, vertidos,
    o vigilancia. Incrementa la presión antrópica localizada.
    """
    os.makedirs("data", exist_ok=True)

    if os.path.exists(LOITERING_CACHE):
        age = time.time() - os.path.getmtime(LOITERING_CACHE)
        if age < LOITERING_EXPIRY:
            try:
                with open(LOITERING_CACHE, "r") as f:
                    cached = json.load(f)
                logger.info(f"[Loitering] Usando caché ({len(cached)} eventos)")
                return cached
            except json.JSONDecodeError:
                pass

    token = os.environ.get("GFW_API_TOKEN")
    if not token:
        logger.warning("[Loitering] GFW_API_TOKEN no disponible.")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    params: dict = {
        "datasets":   "public-global-loitering-events:latest",
        "limit":      min(limit, 50),
        "offset":     0,
        "start-date": start_date,
        "end-date":   end_date,
    }
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        params["bbox"] = f"{min_lon},{min_lat},{max_lon},{max_lat}"

    all_loitering: list[dict] = []
    url = f"{GFW_BASE_URL}/v3/events"

    try:
        while len(all_loitering) < limit:
            logger.info(
                f"[Loitering] Consultando loitering "
                f"(offset={params['offset']})..."
            )
            data = http_get(url, params=params, token=token, timeout=25)
            if data is None:
                break

            entries = data.get("entries", [])
            if not entries:
                break

            for ev in entries:
                pos = ev.get("position", {}) or {}
                lat = pos.get("lat")
                lon = pos.get("lon")
                vessel = ev.get("vessel", {}) or {}

                start = ev.get("start", "")
                end_t = ev.get("end", "")
                duration_h = 0.0
                try:
                    from datetime import datetime
                    fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
                    t0 = datetime.strptime(start, fmt)
                    t1 = datetime.strptime(end_t, fmt)
                    duration_h = (t1 - t0).total_seconds() / 3600.0
                except Exception:
                    pass

                all_loitering.append({
                    "loitering_id": ev.get("id", ""),
                    "vessel_id":    vessel.get("id", ""),
                    "mmsi":         vessel.get("ssvid", ""),
                    "shipname":     vessel.get("name", ""),
                    "flag":         vessel.get("flag", ""),
                    "lat":          lat,
                    "lon":          lon,
                    "start":        start,
                    "end":          end_t,
                    "duration_h":   round(duration_h, 2),
                    "source":       "GFW_loitering",
                })

            total = data.get("total", 0)
            next_offset = params["offset"] + params["limit"]
            if next_offset < total and next_offset < limit:
                params["offset"] = next_offset
            else:
                break

        with open(LOITERING_CACHE, "w") as f:
            json.dump(all_loitering, f, indent=2)
        logger.info(f"[Loitering] {len(all_loitering)} eventos de merodeo encontrados.")

    except Exception as exc:
        import logging as _lg; _lg.getLogger(__name__).error("Pipeline error: %s", exc)

    return all_loitering


# ================================================================
# FUENTE 9: GFW — Fishing Effort Report (4Wings)
# ================================================================
FISHING_EFFORT_CACHE  = "data/gfw_fishing_effort_cache.json"
FISHING_EFFORT_EXPIRY = 21600   # 6 horas

def fetch_fishing_effort_report(
    polygon_coords: list[list[float]] | None = None,
    eez_id: int | None = 8383,
    start_date: str = "2023-01-01",
    end_date:   str = "2023-12-31",
    group_by: str = "gearType",
    spatial_resolution: str = "low",
    temporal_resolution: str = "yearly",
) -> list[dict]:
    """
    Genera un reporte de esfuerzo pesquero aparente usando el endpoint 4Wings.
    Dataset: public-global-fishing-effort:latest

    El esfuerzo pesquero es un proxy de productividad biológica:
    zonas con más pesca tienden a tener más biomasa y más megafauna.
    """
    os.makedirs("data", exist_ok=True)

    if os.path.exists(FISHING_EFFORT_CACHE):
        age = time.time() - os.path.getmtime(FISHING_EFFORT_CACHE)
        if age < FISHING_EFFORT_EXPIRY:
            try:
                with open(FISHING_EFFORT_CACHE, "r") as f:
                    cached = json.load(f)
                logger.info(f"[Fishing Effort] Usando caché ({len(cached)} celdas)")
                return cached
            except json.JSONDecodeError:
                pass

    token = os.environ.get("GFW_API_TOKEN")
    if not token:
        logger.warning("[Fishing Effort] GFW_API_TOKEN no disponible.")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    query_params: dict = {
        "datasets[0]":         "public-global-fishing-effort:latest",
        "start-date":          start_date,
        "end-date":            end_date,
        "spatial-resolution":  spatial_resolution,
        "temporal-resolution": temporal_resolution,
        "group-by":            group_by,
    }

    if polygon_coords:
        body = {
            "region": {
                "type": "Feature",
                "geometry": {
                    "type":        "Polygon",
                    "coordinates": [polygon_coords],
                },
            }
        }
    else:
        body = {
            "region": {
                "dataset": "public-eez-areas:v12",
                "id":      eez_id,
            }
        }

    url = f"{GFW_BASE_URL}/v3/4wings/report"
    all_cells: list[dict] = []

    try:
        logger.info(
            f"[Fishing Effort] Solicitando esfuerzo pesquero "
            f"({start_date} → {end_date}, group={group_by})..."
        )
        raw = http_post(url, json=body, params=query_params, token=token, timeout=60)
        if raw is None:
            return all_cells

        entries = raw if isinstance(raw, list) else raw.get("entries", [raw])

        for cell in entries:
            if not isinstance(cell, dict):
                continue
            all_cells.append({
                "h3_index":        cell.get("h3", cell.get("cellId", "")),
                "lat":             cell.get("lat"),
                "lon":             cell.get("lon"),
                "fishing_hours":   cell.get("hours", 0),
                "group":           cell.get("group", ""),
                "period":          cell.get("period", ""),
                "source":          "GFW_fishing_effort",
            })

        with open(FISHING_EFFORT_CACHE, "w") as f:
            json.dump(all_cells, f, indent=2)
        logger.info(f"[Fishing Effort] {len(all_cells)} celdas de esfuerzo pesquero.")

    except Exception as exc:
        import logging as _lg; _lg.getLogger(__name__).error("Pipeline error: %s", exc)

    return all_cells
