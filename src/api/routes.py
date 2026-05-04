"""
ocean_proto / src / api / routes.py — GFW-ONLY
===============================================
API REST usando exclusivamente datos de Global Fishing Watch.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import json
import os
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
    Endpoint principal: Devuelve los Pressure Hotspots (IPA) en GeoJSON.
    Cada feature contiene h3_index, vessel_count, ipa_100, ipa_level.
    """
    return _load_geojson("data/risk_hotspots.geojson")


@router.get("/api/vessels")
async def get_vessels():
    """Devuelve las posiciones de los buques (GFW SAR) como GeoJSON."""
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


# --- Alias legacy ---
@router.get("/api/v1/hotspots")
async def get_hotspots_v1():
    return _load_geojson("data/risk_hotspots.geojson")


@router.get("/api/oil-platforms")
async def get_oil_platforms():
    """Devuelve las plataformas O&G en caché como GeoJSON."""
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
                    "source": p.get("source", ""),
                }
            }
            features.append(feat)
        except (KeyError, ValueError, TypeError):
            continue
    return {"type": "FeatureCollection", "features": features}


@router.get("/api/support-vessels")
async def get_support_vessels():
    """Devuelve los buques de apoyo O&G (OSVs) en caché como GeoJSON."""
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
    """Devuelve los AIS gap events como GeoJSON."""
    return _load_cached_events("data/gfw_gap_events_cache.json", "gap")


@router.get("/api/encounters")
async def get_encounters():
    """Devuelve los encounter events (transbordo potencial) como GeoJSON."""
    return _load_cached_events("data/gfw_encounters_cache.json", "encounter")


@router.get("/api/loitering")
async def get_loitering():
    """Devuelve los loitering events (merodeo) como GeoJSON."""
    return _load_cached_events("data/gfw_loitering_cache.json", "loitering")


def _load_cached_events(filepath: str, event_type: str) -> dict:
    """Helper genérico para cargar eventos GFW cacheados como GeoJSON."""
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}
    try:
        with open(filepath, 'r') as f:
            events = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"type": "FeatureCollection", "features": []}
    features = []
    for ev in events:
        try:
            lat = ev.get("lat")
            lon = ev.get("lon")
            if lat is None or lon is None:
                continue
            props = {k: v for k, v in ev.items() if k not in ("lat", "lon")}
            props["event_type"] = event_type
            feat = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(lon), float(lat)]
                },
                "properties": props,
            }
            features.append(feat)
        except (KeyError, ValueError, TypeError):
            continue
    return {"type": "FeatureCollection", "features": features}


def update_pipeline_task(build_kg: bool = False):
    """Tarea en segundo plano: re-ingesta GFW-only + recalcula IPA."""
    try:
        from src.pipeline.ingest import run_ingestion
        from datetime import datetime
        logger.info("Iniciando actualización GFW-Only...")

        (gfw, platforms, support, gaps,
         encounters, loitering, effort, heatmap) = run_ingestion()

        from src.pipeline.spatial_join import compute_gfw_only_hotspots
        current_month = datetime.now().month
        compute_gfw_only_hotspots(
            gfw,
            gaps_gdf=gaps,
            encounters_gdf=encounters,
            loitering_gdf=loitering,
            platforms_gdf=platforms,
            support_gdf=support,
            fishing_effort_df=effort,
            presence_df=heatmap,
            output_path='data/risk_hotspots.geojson',
            analysis_month=current_month,
        )
        logger.info("Pipeline GFW-Only completado (IPA).")

        if build_kg:
            from src.pipeline.knowledge_graph import build_and_export
            logger.info("Construyendo Knowledge Graph...")
            gfw_df = pd.DataFrame(gfw.drop(columns='geometry', errors='ignore'))
            platforms_df = pd.DataFrame(platforms.drop(columns='geometry', errors='ignore'))
            support_df = pd.DataFrame(support.drop(columns='geometry', errors='ignore'))
            gaps_df = pd.DataFrame(gaps.drop(columns='geometry', errors='ignore'))
            hotspots_df = None
            if os.path.exists('data/risk_hotspots.geojson'):
                gdf = gpd.read_file('data/risk_hotspots.geojson')
                hotspots_df = pd.DataFrame(gdf.drop(columns='geometry', errors='ignore'))
            build_and_export(
                gfw_df, pd.DataFrame(),  # empty obis
                platforms_df=platforms_df,
                support_df=support_df,
                gaps_df=gaps_df,
                hotspots_df=hotspots_df,
                out_dir=KG_DIR,
            )
            logger.info("Knowledge Graph construido.")
    except Exception as e:
        logger.error(f"Error ejecutando el pipeline: {e}", exc_info=True)


@router.post("/api/refresh")
async def trigger_refresh(
    background_tasks: BackgroundTasks,
    build_kg: bool = False,
):
    """
    Lanza el pipeline GFW-Only en segundo plano.
    - build_kg=true → también reconstruye el Knowledge Graph.
    """
    background_tasks.add_task(update_pipeline_task, build_kg)
    msg = "Pipeline GFW-Only (IPA) lanzado en segundo plano"
    if build_kg:
        msg += " + Knowledge Graph"
    return {"status": "processing", "message": msg}


@router.get("/api/seasonal/{month}")
async def get_seasonal_summary(month: int):
    """Devuelve el resumen de estacionalidad pesquera para un mes dado."""
    if not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
    try:
        from src.pipeline.seasonal import compute_seasonal_summary
        return compute_seasonal_summary(month)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/acoustic-risk")
async def get_acoustic_risk():
    """Devuelve el nivel de ruido acústico estimado por celda H3 como GeoJSON."""
    filepath = "data/gfw_data.csv"
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}
    try:
        import h3 as h3lib
        from src.pipeline.acoustic_model import compute_acoustic_risk_per_hex
        from src.pipeline.spatial_join import get_h3_index, cell_to_polygon, H3_RESOLUTION

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


# ── Knowledge Graph endpoints ────────────────────────────────────────────────

@router.get("/api/knowledge-graph")
async def get_knowledge_graph():
    """Devuelve el Knowledge Graph en formato graph.json."""
    path = os.path.join(KG_DIR, "graph.json")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail="Knowledge Graph no encontrado. Ejecuta POST /api/refresh?build_kg=true"
        )
    return FileResponse(path, media_type="application/json")


@router.get("/api/graph/stats")
async def get_graph_stats():
    """Devuelve estadísticas resumidas del Knowledge Graph."""
    path = os.path.join(KG_DIR, "graph.json")
    if not os.path.exists(path):
        return {"status": "not_built", "nodes": 0, "edges": 0, "node_types": {}}
    try:
        with open(path) as f:
            data = json.load(f)
        nodes = data.get("nodes", [])
        links = data.get("links", [])
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
    """Devuelve el GRAPH_REPORT.md como texto plano."""
    path = os.path.join(KG_DIR, "GRAPH_REPORT.md")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    return FileResponse(path, media_type="text/markdown")


# ── GEMINI AI Endpoints ───────────────────────────────────────────────────────

@router.get("/api/ai/status")
async def get_ai_status():
    """Verifica la conectividad con Gemini. Retorna latencia y estado."""
    try:
        from src.pipeline.gemini_analyst import quick_status
        return quick_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/ai/analyze/{h3_index}")
async def analyze_cell(h3_index: str):
    """Análisis narrativo de riesgo para una celda H3 específica."""
    gj = _load_geojson("data/risk_hotspots.geojson")
    cell_props = {}
    for feat in gj.get("features", []):
        if feat.get("properties", {}).get("h3_index") == h3_index:
            cell_props = feat["properties"]
            break
    if not cell_props:
        cell_props = {"h3_index": h3_index, "vessel_count": 0, "ipa_100": 0}
    try:
        from src.pipeline.gemini_analyst import analyze_hotspot
        from datetime import datetime
        result = analyze_hotspot(
            h3_index     = h3_index,
            ipa_score    = float(cell_props.get("ipa_100", 0)),
            vessel_count = int(cell_props.get("vessel_count", 0)),
            gap_count    = int(cell_props.get("gap_count", 0)),
            enc_count    = int(cell_props.get("encounter_count", 0)),
            loi_count    = int(cell_props.get("loitering_count", 0)),
            month        = datetime.now().month,
        )
        return {"h3_index": h3_index, "cell_data": cell_props, "analysis": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/ai/region-summary")
async def get_region_summary():
    """Resumen ejecutivo del área de estudio para grant proposals."""
    try:
        from src.pipeline.gemini_analyst import synthesize_region
        return synthesize_region(top_n=5)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/ai/methods")
async def get_methods_text():
    """Párrafo de Métodos para paper científico sobre el IPA."""
    try:
        from src.pipeline.gemini_analyst import explain_ipa_for_paper
        text = explain_ipa_for_paper()
        return {"methods_text": text, "word_count": len(text.split())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/ai/top-hotspots")
async def analyze_top_hotspots(limit: int = 3):
    """Análisis Gemini de las N celdas de mayor presión antrópica."""
    from datetime import datetime
    gj = _load_geojson("data/risk_hotspots.geojson")
    features = sorted(
        gj.get("features", []),
        key=lambda x: x.get("properties", {}).get("ipa_100", 0),
        reverse=True,
    )[:limit]
    if not features:
        return {"analyses": [], "message": "No hotspot data. Run POST /api/refresh first."}
    try:
        from src.pipeline.gemini_analyst import analyze_hotspot
        month = datetime.now().month
        analyses = []
        for feat in features:
            props = feat.get("properties", {})
            analysis = analyze_hotspot(
                h3_index     = props.get("h3_index", ""),
                ipa_score    = float(props.get("ipa_100", 0)),
                vessel_count = int(props.get("vessel_count", 0)),
                gap_count    = int(props.get("gap_count", 0)),
                enc_count    = int(props.get("encounter_count", 0)),
                loi_count    = int(props.get("loitering_count", 0)),
                month        = month,
            )
            analyses.append({
                "h3_index":  props.get("h3_index"),
                "ipa_100":   props.get("ipa_100"),
                "ipa_level": props.get("ipa_level"),
                "analysis":  analysis,
            })
        return {"analyses": analyses, "count": len(analyses)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
