from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import json
import os
from .models import FeatureCollection, VesselRecord
from typing import List
import pandas as pd
import geopandas as gpd
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

KG_DIR = "data/knowledge_graph"

def _load_geojson(filepath: str) -> dict:
    """Carga el GeoJSON de hotspots desde disco."""
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}
    with open(filepath, 'r') as f:
        return json.load(f)


@router.get("/api/risk-hotspots")
async def get_risk_hotspots():
    """
    Endpoint principal del frontend: Devuelve los Risk Hotspots en GeoJSON.
    Cada feature contiene h3_index, vessel_count, megafauna_count, risk_score.
    """
    return _load_geojson("data/risk_hotspots.geojson")


@router.get("/api/megafauna")
async def get_megafauna():
    """
    Devuelve los avistamientos de megafauna (OBIS) como GeoJSON de puntos.
    """
    filepath = "data/obis_data.csv"
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}

    df = pd.read_csv(filepath)
    features = []
    for _, row in df.iterrows():
        try:
            feat = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["decimalLongitude"]), float(row["decimalLatitude"])]
                },
                "properties": {
                    "species": row.get("species", "Unknown"),
                    "eventDate": str(row.get("eventDate", ""))
                }
            }
            features.append(feat)
        except (KeyError, ValueError):
            continue
    return {"type": "FeatureCollection", "features": features}


@router.get("/api/vessels")
async def get_vessels():
    """
    Devuelve las posiciones actuales de los buques (GFW) como GeoJSON de puntos.
    """
    filepath = "data/gfw_data.csv"
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}

    df = pd.read_csv(filepath)
    features = []
    for _, row in df.iterrows():
        try:
            feat = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["lon"]), float(row["lat"])]
                },
                "properties": {
                    "mmsi": str(row.get("mmsi", "")),
                    "vessel_type": str(row.get("vessel_type", "unknown")),
                    "timestamp": str(row.get("timestamp", ""))
                }
            }
            features.append(feat)
        except (KeyError, ValueError):
            continue
    return {"type": "FeatureCollection", "features": features}


# --- Alias legacy /api/v1/* para compatibilidad ---
@router.get("/api/v1/hotspots")
async def get_hotspots_v1():
    return _load_geojson("data/risk_hotspots.geojson")


@router.get("/api/oil-platforms")
async def get_oil_platforms():
    """
    Devuelve las plataformas O&G cargadas en caché como GeoJSON de puntos.
    Fuente: BOEM ArcGIS REST + CSV manual del portal GFW.
    """
    filepath = "data/gfw_oil_platforms_cache.json"
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}
    try:
        with open(filepath, 'r') as f:
            platforms = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"type": "FeatureCollection", "features": []}
    features = []
    for p in platforms:
        try:
            feat = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(p["lon"]), float(p["lat"])]
                },
                "properties": {
                    "platform_id": p.get("platform_id", ""),
                    "category": p.get("category", "OIL"),
                    "label": p.get("label", ""),
                    "sub_category": p.get("sub_category", ""),
                    "source": p.get("source", ""),
                }
            }
            features.append(feat)
        except (KeyError, ValueError, TypeError):
            continue
    return {"type": "FeatureCollection", "features": features}


@router.get("/api/support-vessels")
async def get_support_vessels():
    """
    Devuelve los buques de apoyo O&G (OSVs) en caché como GeoJSON.
    Fuente: GFW Support Vessels dataset.
    """
    filepath = "data/gfw_support_vessels_cache.json"
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}
    try:
        with open(filepath, 'r') as f:
            vessels = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"type": "FeatureCollection", "features": []}
    features = []
    for v in vessels:
        try:
            lat = v.get("lat")
            lon = v.get("lon")
            if lat is None or lon is None:
                continue
            feat = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(lon), float(lat)]
                },
                "properties": {
                    "vessel_id": v.get("vessel_id", ""),
                    "mmsi": v.get("mmsi", ""),
                    "shipname": v.get("shipname", ""),
                    "flag": v.get("flag", ""),
                    "vessel_type": v.get("vessel_type", "support"),
                    "source": v.get("source", ""),
                }
            }
            features.append(feat)
        except (KeyError, ValueError, TypeError):
            continue
    return {"type": "FeatureCollection", "features": features}


@router.get("/api/gap-events")
async def get_gap_events():
    """
    Devuelve los AIS gap events (apagones de transpondedor) como GeoJSON.
    Fuente: GFW Global Gaps Events dataset.
    """
    filepath = "data/gfw_gap_events_cache.json"
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}
    try:
        with open(filepath, 'r') as f:
            gaps = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"type": "FeatureCollection", "features": []}
    features = []
    for g in gaps:
        try:
            lat = g.get("lat")
            lon = g.get("lon")
            if lat is None or lon is None:
                continue
            feat = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(lon), float(lat)]
                },
                "properties": {
                    "gap_id": g.get("gap_id", ""),
                    "mmsi": g.get("mmsi", ""),
                    "shipname": g.get("shipname", ""),
                    "flag": g.get("flag", ""),
                    "gap_hours": g.get("gap_hours", 0),
                    "start": g.get("start", ""),
                    "end": g.get("end", ""),
                    "source": g.get("source", ""),
                }
            }
            features.append(feat)
        except (KeyError, ValueError, TypeError):
            continue
    return {"type": "FeatureCollection", "features": features}


def update_pipeline_task(build_kg: bool = False, enhanced: bool = True):
    """Tarea en segundo plano: re-ingesta, recalcula hotspots (con criterios oceanográficos
    si enhanced=True) y opcionalmente construye el KG."""
    try:
        from src.pipeline.ingest import run_ingestion
        from datetime import datetime
        logger.info("Iniciando actualización de datos geoespaciales...")
        gfw, obis, platforms, support, gaps = run_ingestion('data/obis_data.csv')

        if enhanced:
            from src.pipeline.spatial_join import compute_enhanced_risk_hotspots
            current_month = datetime.now().month
            compute_enhanced_risk_hotspots(
                gfw, obis, gaps_gdf=gaps,
                output_path='data/risk_hotspots.geojson',
                analysis_month=current_month,
            )
            logger.info("Actualización geoespacial ENHANCED completada (criterios oceanográficos).")
        else:
            from src.pipeline.spatial_join import compute_risk_hotspots
            compute_risk_hotspots(gfw, obis, 'data/risk_hotspots.geojson')
            logger.info("Actualización geoespacial baseline completada.")

        if build_kg:
            from src.pipeline.knowledge_graph import build_and_export
            logger.info("Construyendo Knowledge Graph v3...")
            gfw_df       = pd.DataFrame(gfw.drop(columns='geometry', errors='ignore'))
            obis_df      = pd.DataFrame(obis.drop(columns='geometry', errors='ignore'))
            platforms_df  = pd.DataFrame(platforms.drop(columns='geometry', errors='ignore'))
            support_df    = pd.DataFrame(support.drop(columns='geometry', errors='ignore'))
            gaps_df       = pd.DataFrame(gaps.drop(columns='geometry', errors='ignore'))
            hotspots_df = None
            if os.path.exists('data/risk_hotspots.geojson'):
                gdf = gpd.read_file('data/risk_hotspots.geojson')
                hotspots_df = pd.DataFrame(gdf.drop(columns='geometry', errors='ignore'))
            build_and_export(
                gfw_df, obis_df,
                platforms_df=platforms_df,
                support_df=support_df,
                gaps_df=gaps_df,
                hotspots_df=hotspots_df,
                out_dir=KG_DIR,
            )
            logger.info("Knowledge Graph v3 construido exitosamente.")
    except Exception as e:
        logger.error(f"Error ejecutando el pipeline: {e}", exc_info=True)


@router.post("/api/refresh")
async def trigger_refresh(
    background_tasks: BackgroundTasks,
    build_kg: bool = False,
    enhanced: bool = True,
):
    """
    Lanza el pipeline de ingesta + spatial join en segundo plano.
    - build_kg=true  → también reconstruye el Knowledge Graph.
    - enhanced=true  → usa criterios oceanográficos (SST, Chl-a, acústico, etc.).
    - enhanced=false → solo score baseline vessel × megafauna.
    """
    background_tasks.add_task(update_pipeline_task, build_kg, enhanced)
    msg = (
        "Pipeline ENHANCED (criterios oceanográficos) lanzado"
        if enhanced else
        "Pipeline baseline lanzado en segundo plano"
    )
    if build_kg:
        msg += " + Knowledge Graph"
    return {"status": "processing", "message": msg}


@router.get("/api/knowledge-graph")
async def get_knowledge_graph():
    """
    Devuelve el Knowledge Graph en formato graph.json (NetworkX node-link).
    Compatible con Graphify y con D3.js force-directed graph.
    """
    path = os.path.join(KG_DIR, "graph.json")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail="Knowledge Graph no encontrado. Ejecuta POST /api/refresh?build_kg=true"
        )
    return FileResponse(path, media_type="application/json")


@router.get("/api/graph/stats")
async def get_graph_stats():
    """
    Devuelve estadísticas resumidas del Knowledge Graph (nodos, aristas, tipos).
    """
    path = os.path.join(KG_DIR, "graph.json")
    if not os.path.exists(path):
        return {"status": "not_built", "nodes": 0, "edges": 0, "node_types": {}}
    try:
        with open(path) as f:
            data = json.load(f)
        nodes      = data.get("nodes", [])
        links      = data.get("links", [])
        node_types: dict = {}
        for n in nodes:
            t = n.get("type", "Unknown")
            node_types[t] = node_types.get(t, 0) + 1
        return {
            "status":     "ready",
            "nodes":      len(nodes),
            "edges":      len(links),
            "node_types": node_types,
            "graph_name": data.get("graph", {}).get("name", ""),
            "created":    data.get("graph", {}).get("created", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/graph/report")
async def get_graph_report():
    """
    Devuelve el GRAPH_REPORT.md como texto plano.
    """
    path = os.path.join(KG_DIR, "GRAPH_REPORT.md")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    return FileResponse(path, media_type="text/markdown")


# ── Nuevos endpoints: Criterios Oceanográficos ────────────────────────────────

@router.get("/api/oceanographic/sst")
async def get_sst(use_cache: bool = True):
    """
    Devuelve temperatura superficial del mar (SST) del área de interés.
    Fuente: NOAA OISST v2.1 via ERDDAP. Caché local de 24h.
    """
    try:
        from src.pipeline.oceanographic import fetch_sst_erddap
        df = fetch_sst_erddap(use_cache=use_cache)
        if df.empty:
            return {"status": "no_data", "features": []}
        features = []
        for _, row in df.iterrows():
            try:
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(row["longitude"]), float(row["latitude"])]
                    },
                    "properties": {
                        "time":         str(row.get("time", "")),
                        "sst":          round(float(row.get("sst", 0)), 2),
                        "sst_anomaly":  round(float(row.get("sst_anomaly", 0) or 0), 2),
                    }
                })
            except (ValueError, TypeError):
                continue
        return {"type": "FeatureCollection", "features": features, "count": len(features)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/oceanographic/chlorophyll")
async def get_chlorophyll(use_cache: bool = True):
    """
    Devuelve concentración de Clorofila-a (mg/m³).
    Fuente: MODIS Aqua 8-day composite via ERDDAP. Caché de 8 días.
    """
    try:
        from src.pipeline.oceanographic import fetch_chlorophyll_erddap
        df = fetch_chlorophyll_erddap(use_cache=use_cache)
        if df.empty:
            return {"status": "no_data", "features": []}
        features = []
        for _, row in df.iterrows():
            try:
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(row["longitude"]), float(row["latitude"])]
                    },
                    "properties": {
                        "time":             str(row.get("time", "")),
                        "chlorophyll_mg_m3": round(float(row.get("chlorophyll_mg_m3", 0)), 4),
                    }
                })
            except (ValueError, TypeError):
                continue
        return {"type": "FeatureCollection", "features": features, "count": len(features)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/oceanographic/bathymetry")
async def get_bathymetry(use_cache: bool = True):
    """
    Devuelve datos batimétricos del área (ETOPO2022).
    Los datos son estáticos — la caché es permanente hasta ser borrada.
    """
    try:
        from src.pipeline.oceanographic import fetch_bathymetry_erddap
        df = fetch_bathymetry_erddap(use_cache=use_cache)
        if df.empty:
            return {"status": "no_data", "features": []}
        features = []
        for _, row in df.iterrows():
            try:
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(row["longitude"]), float(row["latitude"])]
                    },
                    "properties": {
                        "depth_m":      round(float(row.get("depth_m", 0) or 0), 1),
                        "elevation_m":  round(float(row.get("elevation_m", 0) or 0), 1),
                    }
                })
            except (ValueError, TypeError):
                continue
        return {"type": "FeatureCollection", "features": features, "count": len(features)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/seasonal/{month}")
async def get_seasonal_summary(month: int):
    """
    Devuelve el resumen de estacionalidad para un mes dado (1-12).
    Incluye las especies en temporada pico y el multiplicador de riesgo máximo.
    """
    if not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
    try:
        from src.pipeline.seasonal import compute_seasonal_summary
        summary = compute_seasonal_summary(month)
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/acoustic-risk")
async def get_acoustic_risk():
    """
    Devuelve el nivel de ruido acústico estimado por celda H3 como GeoJSON.
    Calcula SPL acumulado en dB re 1μPa basado en las detecciones de embarcaciones.
    """
    filepath = "data/gfw_data.csv"
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}
    try:
        import h3 as h3lib
        from src.pipeline.acoustic_model import compute_acoustic_risk_per_hex
        from src.pipeline.spatial_join import get_h3_index, cell_to_polygon, H3_RESOLUTION
        import geopandas as gpd

        df = pd.read_csv(filepath)
        if df.empty:
            return {"type": "FeatureCollection", "features": []}

        df["h3_index"] = df.apply(
            lambda r: get_h3_index(r["lat"], r["lon"], H3_RESOLUTION), axis=1
        )
        acoustic_df = compute_acoustic_risk_per_hex(df, H3_RESOLUTION)

        features = []
        for _, row in acoustic_df.iterrows():
            try:
                poly = cell_to_polygon(row["h3_index"])
                coords = [list(c) for c in poly.exterior.coords]
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [coords]},
                    "properties": {
                        "h3_index":            row["h3_index"],
                        "vessel_count":        int(row["vessel_count"]),
                        "estimated_spl_db":    float(row["estimated_spl_db"]),
                        "acoustic_risk_level": row["acoustic_risk_level"],
                        "acoustic_risk_score": int(row["acoustic_risk_score"]),
                    }
                })
            except Exception:
                continue
        return {"type": "FeatureCollection", "features": features}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
