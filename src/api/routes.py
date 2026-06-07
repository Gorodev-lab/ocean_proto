"""
ocean_proto / src / api / routes.py
====================================
API REST — GFW + OBIS + Knowledge Graph + AI.

Reglas de concurrencia:
  - Todo I/O de disco (open, json.load, pd.read_csv) se delega a
    `run_in_threadpool` para no bloquear el event loop de uvicorn.
  - Todo I/O de red síncrono (Gemini, pipeline) idem.
  - Los helpers síncronos (_load_geojson, etc.) permanecen síncronos
    pero NUNCA se llaman directamente desde async def — solo vía threadpool.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional

import pandas as pd
import geopandas as gpd
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)
router = APIRouter()

KG_DIR = "data/knowledge_graph"


# ── Helpers síncronos de disco ────────────────────────────────────────────────
# NUNCA llamar directamente desde async def — usar await run_in_threadpool(...)

def _load_geojson(filepath: str) -> dict:
    """Carga un GeoJSON desde disco. Retorna FeatureCollection vacía si no existe."""
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"type": "FeatureCollection", "features": []}


def _load_cached_events(filepath: str, event_type: str) -> dict:
    """Carga eventos GFW cacheados como GeoJSON FeatureCollection."""
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
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
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": props,
            })
        except (KeyError, ValueError, TypeError):
            continue
    return {"type": "FeatureCollection", "features": features}


def _vessels_from_csv() -> dict:
    """Lee el CSV de vessels y lo convierte a GeoJSON."""
    filepath = "data/gfw_data.csv"
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}
    df = pd.read_csv(filepath)
    features = []
    for row in df.itertuples(index=False):
        try:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row.lon), float(row.lat)]},
                "properties": {
                    "mmsi":        str(getattr(row, "mmsi", "")),
                    "vessel_type": str(getattr(row, "vessel_type", "unknown")),
                    "timestamp":   str(getattr(row, "timestamp", "")),
                },
            })
        except (AttributeError, ValueError):
            continue
    return {"type": "FeatureCollection", "features": features}


def _oil_platforms_from_cache() -> dict:
    """Carga plataformas O&G desde caché JSON."""
    filepath = "data/gfw_oil_platforms_cache.json"
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}
    try:
        with open(filepath, "r") as f:
            platforms = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"type": "FeatureCollection", "features": []}

    features = []
    for p in platforms:
        try:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(p["lon"]), float(p["lat"])]},
                "properties": {
                    "platform_id": p.get("platform_id", ""),
                    "category":    p.get("category", "OIL"),
                    "label":       p.get("label", ""),
                    "source":      p.get("source", ""),
                },
            })
        except (KeyError, ValueError, TypeError):
            continue
    return {"type": "FeatureCollection", "features": features}


def _acoustic_risk_geojson() -> dict:
    """Calcula el riesgo acústico por celda H3 desde el CSV de vessels."""
    import h3 as h3lib
    from src.pipeline.acoustic_model import compute_acoustic_risk_per_hex
    from src.pipeline.spatial_join import get_h3_index, cell_to_polygon, H3_RESOLUTION

    filepath = "data/gfw_data.csv"
    if not os.path.exists(filepath):
        return {"type": "FeatureCollection", "features": []}

    df = pd.read_csv(filepath)
    if df.empty:
        return {"type": "FeatureCollection", "features": []}

    df["h3_index"] = df.apply(
        lambda r: get_h3_index(r["lat"], r["lon"], H3_RESOLUTION), axis=1
    )
    acoustic_df = compute_acoustic_risk_per_hex(df, H3_RESOLUTION)

    features = []
    for row in acoustic_df.itertuples(index=False):
        try:
            poly = cell_to_polygon(row.h3_index)
            coords = [list(c) for c in poly.exterior.coords]
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {
                    "h3_index":            row.h3_index,
                    "vessel_count":        int(row.vessel_count),
                    "estimated_spl_db":    float(row.estimated_spl_db),
                    "acoustic_risk_level": row.acoustic_risk_level,
                    "acoustic_risk_score": int(row.acoustic_risk_score),
                },
            })
        except Exception:
            continue
    return {"type": "FeatureCollection", "features": features}


def _graph_stats() -> dict:
    """Lee el graph.json y devuelve estadísticas resumidas."""
    path = os.path.join(KG_DIR, "graph.json")
    if not os.path.exists(path):
        return {"status": "not_built", "nodes": 0, "edges": 0, "node_types": {}}
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


# ── Pipeline de background ────────────────────────────────────────────────────

def _run_pipeline(build_kg: bool = False) -> None:
    """Orquesta la ingesta GFW + cálculo IPA + KG opcional."""
    from src.pipeline.ingest import run_ingestion
    from src.pipeline.spatial_join import compute_gfw_only_hotspots
    from src.api.megafauna_routes import invalidate_megafauna_cache

    logger.info("Pipeline GFW-Only iniciado...")
    (gfw, platforms, support, gaps,
     encounters, loitering, effort, heatmap) = run_ingestion()

    compute_gfw_only_hotspots(
        gfw,
        gaps_gdf=gaps,
        encounters_gdf=encounters,
        loitering_gdf=loitering,
        platforms_gdf=platforms,
        support_gdf=support,
        fishing_effort_df=effort,
        presence_df=heatmap,
        output_path="data/risk_hotspots.geojson",
        analysis_month=datetime.now().month,
    )
    logger.info("Pipeline IPA completado.")

    try:
        invalidate_megafauna_cache()
    except Exception as exc:
        logger.warning("No se pudo invalidar caché de megafauna: %s", exc)

    if build_kg:
        from src.pipeline.knowledge_graph import build_and_export
        logger.info("Construyendo Knowledge Graph...")

        # Evita copias profundas innecesarias — drop in-place sobre vista
        def _to_df(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
            cols = [c for c in gdf.columns if c != "geometry"]
            return gdf[cols].copy()

        hotspots_df: Optional[pd.DataFrame] = None
        if os.path.exists("data/risk_hotspots.geojson"):
            hotspots_df = _to_df(gpd.read_file("data/risk_hotspots.geojson"))

        build_and_export(
            _to_df(gfw),
            pd.DataFrame(),
            platforms_df=_to_df(platforms),
            support_df=_to_df(support),
            gaps_df=_to_df(gaps),
            hotspots_df=hotspots_df,
            out_dir=KG_DIR,
        )
        logger.info("Knowledge Graph construido.")


# ── Endpoints — GeoJSON / datos ───────────────────────────────────────────────

@router.get("/api/risk-hotspots")
async def get_risk_hotspots():
    return await run_in_threadpool(_load_geojson, "data/risk_hotspots.geojson")


@router.get("/api/v1/hotspots")
async def get_hotspots_v1():
    return await run_in_threadpool(_load_geojson, "data/risk_hotspots.geojson")


@router.get("/api/vessels")
async def get_vessels():
    return await run_in_threadpool(_vessels_from_csv)


@router.get("/api/oil-platforms")
async def get_oil_platforms():
    return await run_in_threadpool(_oil_platforms_from_cache)


@router.get("/api/support-vessels")
async def get_support_vessels():
    return await run_in_threadpool(
        _load_cached_events, "data/gfw_support_vessels_cache.json", "support"
    )


@router.get("/api/gap-events")
async def get_gap_events():
    return await run_in_threadpool(
        _load_cached_events, "data/gfw_gap_events_cache.json", "gap"
    )


@router.get("/api/encounters")
async def get_encounters():
    return await run_in_threadpool(
        _load_cached_events, "data/gfw_encounters_cache.json", "encounter"
    )


@router.get("/api/loitering")
async def get_loitering():
    return await run_in_threadpool(
        _load_cached_events, "data/gfw_loitering_cache.json", "loitering"
    )


@router.get("/api/acoustic-risk")
async def get_acoustic_risk():
    try:
        return await run_in_threadpool(_acoustic_risk_geojson)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Endpoints — Pipeline ──────────────────────────────────────────────────────

@router.post("/api/refresh")
async def trigger_refresh(
    background_tasks: BackgroundTasks,
    build_kg: bool = False,
):
    """Lanza el pipeline GFW-Only en segundo plano."""
    background_tasks.add_task(_run_pipeline, build_kg)
    msg = "Pipeline GFW-Only (IPA) lanzado en segundo plano"
    if build_kg:
        msg += " + Knowledge Graph"
    return {"status": "processing", "message": msg}


@router.get("/api/seasonal/{month}")
async def get_seasonal_summary(month: int):
    if not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
    from src.pipeline.seasonal import compute_seasonal_summary
    try:
        return await run_in_threadpool(compute_seasonal_summary, month)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Endpoints — Knowledge Graph ───────────────────────────────────────────────

@router.get("/api/knowledge-graph")
async def get_knowledge_graph():
    path = os.path.join(KG_DIR, "graph.json")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail="Knowledge Graph no encontrado. Ejecuta POST /api/refresh?build_kg=true",
        )
    return FileResponse(path, media_type="application/json")


@router.get("/api/graph/stats")
async def get_graph_stats():
    return await run_in_threadpool(_graph_stats)


@router.get("/api/graph/report")
async def get_graph_report():
    path = os.path.join(KG_DIR, "GRAPH_REPORT.md")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    return FileResponse(path, media_type="text/markdown")


# ── Endpoints — Gemini AI ─────────────────────────────────────────────────────
# Todo I/O de Gemini es síncrono (time.sleep en retries) → run_in_threadpool obligatorio.

@router.get("/api/ai/status")
async def get_ai_status():
    from src.pipeline.gemini_analyst import quick_status
    try:
        return await run_in_threadpool(quick_status)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/ai/analyze/{h3_index}")
async def analyze_cell(h3_index: str):
    from src.pipeline.gemini_analyst import analyze_hotspot

    gj = await run_in_threadpool(_load_geojson, "data/risk_hotspots.geojson")
    cell_props = next(
        (f["properties"] for f in gj.get("features", [])
         if f.get("properties", {}).get("h3_index") == h3_index),
        {"h3_index": h3_index, "vessel_count": 0, "ipa_100": 0},
    )
    try:
        result = await run_in_threadpool(
            analyze_hotspot,
            h3_index,
            float(cell_props.get("ipa_100", 0)),
            int(cell_props.get("vessel_count", 0)),
            int(cell_props.get("gap_count", 0)),
            int(cell_props.get("encounter_count", 0)),
            int(cell_props.get("loitering_count", 0)),
            datetime.now().month,
        )
        return {"h3_index": h3_index, "cell_data": cell_props, "analysis": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/ai/region-summary")
async def get_region_summary():
    from src.pipeline.gemini_analyst import synthesize_region
    try:
        return await run_in_threadpool(synthesize_region, 5)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/ai/methods")
async def get_methods_text():
    from src.pipeline.gemini_analyst import explain_ipa_for_paper
    try:
        text = await run_in_threadpool(explain_ipa_for_paper)
        return {"methods_text": text, "word_count": len(text.split())}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/ai/top-hotspots")
async def analyze_top_hotspots(limit: int = 3):
    from src.pipeline.gemini_analyst import analyze_hotspot

    gj = await run_in_threadpool(_load_geojson, "data/risk_hotspots.geojson")
    features = sorted(
        gj.get("features", []),
        key=lambda x: x.get("properties", {}).get("ipa_100", 0),
        reverse=True,
    )[:limit]

    if not features:
        return {"analyses": [], "message": "No hotspot data. Run POST /api/refresh first."}

    month = datetime.now().month
    analyses = []
    for feat in features:
        props = feat.get("properties", {})
        try:
            analysis = await run_in_threadpool(
                analyze_hotspot,
                props.get("h3_index", ""),
                float(props.get("ipa_100", 0)),
                int(props.get("vessel_count", 0)),
                int(props.get("gap_count", 0)),
                int(props.get("encounter_count", 0)),
                int(props.get("loitering_count", 0)),
                month,
            )
            analyses.append({
                "h3_index":  props.get("h3_index"),
                "ipa_100":   props.get("ipa_100"),
                "ipa_level": props.get("ipa_level"),
                "analysis":  analysis,
            })
        except Exception as exc:
            logger.warning("Gemini falló para %s: %s", props.get("h3_index"), exc)

    return {"analyses": analyses, "count": len(analyses)}
