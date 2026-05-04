"""
ocean_proto / src / pipeline / spatial_join.py — GFW-ONLY
=========================================================
Módulo de cruce espacial usando celdas H3.

Versión GFW-Only: calcula hotspots de presión antrópica usando
exclusivamente datos de Global Fishing Watch (sin OBIS ni ERDDAP).
"""
import h3
import geopandas as gpd
import pandas as pd
import logging
from typing import Optional
from shapely.geometry import Polygon
import json

logger = logging.getLogger(__name__)

H3_RESOLUTION = 5  # ~50 km de diámetro por celda


def get_h3_index(lat: float, lon: float, resolution: int) -> str:
    """Calcula el índice H3 para una coordenada."""
    return h3.latlng_to_cell(lat, lon, resolution)


def cell_to_polygon(hex_id: str) -> Polygon:
    """Convierte un índice H3 hexagonal en un polígono de Shapely."""
    boundary = h3.cell_to_boundary(hex_id)
    lng_lat_boundary = [(lng, lat) for lat, lng in boundary]
    return Polygon(lng_lat_boundary)


def _assign_h3(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Asigna celdas H3 a un GeoDataFrame si no las tiene."""
    if gdf.empty:
        return gdf
    gdf = gdf.copy()
    if "h3_index" not in gdf.columns:
        gdf["h3_index"] = gdf.geometry.apply(
            lambda p: get_h3_index(p.y, p.x, H3_RESOLUTION)
        )
    return gdf


def _count_by_hex(gdf: gpd.GeoDataFrame, count_col: str) -> pd.DataFrame:
    """Cuenta ocurrencias por celda H3."""
    if gdf.empty:
        return pd.DataFrame(columns=["h3_index", count_col])
    gdf = _assign_h3(gdf)
    return gdf.groupby("h3_index").size().reset_index(name=count_col)


def compute_pressure_hotspots(
    gfw_gdf:         gpd.GeoDataFrame,
    output_path:     str = "data/risk_hotspots.geojson",
) -> Optional[gpd.GeoDataFrame]:
    """
    Calcula hotspots de presión de tráfico naval usando solo datos SAR/AIS.

    Es la versión baseline del IPA: solo cuenta embarcaciones por celda H3.
    """
    if not gfw_gdf.empty:
        gfw_gdf = _assign_h3(gfw_gdf)
        vessel_counts = gfw_gdf.groupby("h3_index").size().reset_index(name="vessel_count")
    else:
        vessel_counts = pd.DataFrame(columns=["h3_index", "vessel_count"])

    if vessel_counts.empty:
        gdf_out = gpd.GeoDataFrame(
            columns=["h3_index", "vessel_count", "geometry"],
            crs="EPSG:4326",
        )
        gdf_out.to_file(output_path, driver="GeoJSON")
        return gdf_out

    vessel_counts["vessel_count"] = vessel_counts["vessel_count"].astype(int)
    vessel_counts["geometry"] = vessel_counts["h3_index"].apply(cell_to_polygon)
    gdf_out = gpd.GeoDataFrame(vessel_counts, geometry="geometry", crs="EPSG:4326")
    gdf_out.sort_values("vessel_count", ascending=False, inplace=True)
    gdf_out.reset_index(drop=True, inplace=True)
    gdf_out.to_file(output_path, driver="GeoJSON")
    return gdf_out


def compute_gfw_only_hotspots(
    gfw_gdf:           gpd.GeoDataFrame,
    gaps_gdf:          gpd.GeoDataFrame = None,
    encounters_gdf:    gpd.GeoDataFrame = None,
    loitering_gdf:     gpd.GeoDataFrame = None,
    platforms_gdf:     gpd.GeoDataFrame = None,
    support_gdf:       gpd.GeoDataFrame = None,
    fishing_effort_df: pd.DataFrame     = None,
    presence_df:       pd.DataFrame     = None,
    output_path:       str = "data/risk_hotspots.geojson",
    analysis_month:    int = None,
) -> gpd.GeoDataFrame:
    """
    Versión GFW-Only que integra todos los datasets GFW en el IPA.

    Parámetros
    ----------
    gfw_gdf           : GeoDataFrame con detecciones SAR de embarcaciones
    gaps_gdf          : GeoDataFrame con eventos de apagón AIS
    encounters_gdf    : GeoDataFrame con eventos de encuentro
    loitering_gdf     : GeoDataFrame con eventos de merodeo
    platforms_gdf     : GeoDataFrame con plataformas O&G
    support_gdf       : GeoDataFrame con buques de soporte O&G
    fishing_effort_df : DataFrame tabular de esfuerzo pesquero (4Wings)
    presence_df       : DataFrame tabular de presencia naval (4Wings)
    output_path       : ruta de salida del GeoJSON
    analysis_month    : mes para el modificador temporal (1-12)

    Retorna
    -------
    GeoDataFrame con IPA y sub-scores por celda H3
    """
    # ── Paso 1: Hotspots base (tráfico) ──────────────────────────────────
    base_gdf = compute_pressure_hotspots(gfw_gdf, output_path)

    if base_gdf is None or base_gdf.empty:
        return base_gdf

    # ── Paso 2: gfw_df con h3_index para modelo acústico ─────────────────
    gfw_df = pd.DataFrame()
    if not gfw_gdf.empty:
        gfw_gdf = _assign_h3(gfw_gdf)
        gfw_df = gfw_gdf.drop(columns="geometry", errors="ignore").copy()

    # ── Paso 3: Modelo acústico ──────────────────────────────────────────
    acoustic_df = pd.DataFrame()
    if not gfw_df.empty:
        try:
            from src.pipeline.acoustic_model import compute_acoustic_risk_per_hex
            acoustic_df = compute_acoustic_risk_per_hex(gfw_df, H3_RESOLUTION)
            logger.info(f"[GFW-Only] Modelo acústico: {len(acoustic_df)} celdas.")
        except Exception as e:
            logger.warning(f"[GFW-Only] Modelo acústico falló: {e}")

    # ── Paso 4: Agregar eventos por celda H3 ─────────────────────────────
    gaps_hex_df = _count_by_hex(gaps_gdf, "gap_count") if gaps_gdf is not None else pd.DataFrame()
    encounters_hex_df = _count_by_hex(encounters_gdf, "encounter_count") if encounters_gdf is not None else pd.DataFrame()
    loitering_hex_df = _count_by_hex(loitering_gdf, "loitering_count") if loitering_gdf is not None else pd.DataFrame()
    platforms_hex_df = _count_by_hex(platforms_gdf, "platform_count") if platforms_gdf is not None else pd.DataFrame()
    support_hex_df = _count_by_hex(support_gdf, "support_count") if support_gdf is not None else pd.DataFrame()

    # ── Paso 5: IPA (Índice de Presión Antrópica) ────────────────────────
    hotspots_df = base_gdf.drop(columns="geometry", errors="ignore").copy()
    try:
        from src.pipeline.risk_scoring import compute_anthropic_pressure_index
        ipa_df = compute_anthropic_pressure_index(
            hotspots_df       = hotspots_df,
            acoustic_df       = acoustic_df if not acoustic_df.empty else None,
            gaps_hex_df       = gaps_hex_df if not gaps_hex_df.empty else None,
            encounters_hex_df = encounters_hex_df if not encounters_hex_df.empty else None,
            loitering_hex_df  = loitering_hex_df if not loitering_hex_df.empty else None,
            fishing_effort_df = fishing_effort_df,
            presence_df       = presence_df,
            platforms_hex_df  = platforms_hex_df if not platforms_hex_df.empty else None,
            support_hex_df    = support_hex_df if not support_hex_df.empty else None,
            analysis_month    = analysis_month,
        )
    except Exception as e:
        logger.warning(f"[GFW-Only] IPA falló: {e}. Usando baseline.")
        ipa_df = hotspots_df.copy()
        ipa_df["ipa"]       = ipa_df["vessel_count"]
        ipa_df["ipa_100"]   = ipa_df["vessel_count"]
        ipa_df["ipa_level"] = "MEDIUM"
        ipa_df["crs_100"]   = ipa_df["ipa_100"]
        ipa_df["crs_level"] = ipa_df["ipa_level"]

    # ── Paso 6: Reconstruir GeoDataFrame con geometrías H3 ───────────────
    if not ipa_df.empty:
        ipa_df["geometry"] = ipa_df["h3_index"].apply(cell_to_polygon)
        sort_col = "ipa_100" if "ipa_100" in ipa_df.columns else "vessel_count"
        gdf_out = gpd.GeoDataFrame(ipa_df, geometry="geometry", crs="EPSG:4326")
        gdf_out.sort_values(sort_col, ascending=False, inplace=True)
        gdf_out.reset_index(drop=True, inplace=True)
        gdf_out.to_file(output_path, driver="GeoJSON")
        logger.info(
            f"[GFW-Only] GeoJSON exportado con IPA: {len(gdf_out)} celdas → {output_path}"
        )
        return gdf_out

    return base_gdf


if __name__ == "__main__":
    import logging as _log
    _log.basicConfig(level=_log.INFO)
    from src.pipeline.ingest import run_ingestion
    from datetime import datetime

    print("Ingesting GFW-Only data...")
    (gfw, platforms, support, gaps,
     encounters, loitering, effort, heatmap) = run_ingestion()

    print("Computing GFW-Only pressure hotspots...")
    current_month = datetime.now().month
    compute_gfw_only_hotspots(
        gfw, gaps_gdf=gaps,
        encounters_gdf=encounters,
        loitering_gdf=loitering,
        platforms_gdf=platforms,
        support_gdf=support,
        fishing_effort_df=effort,
        presence_df=heatmap,
        output_path="data/risk_hotspots.geojson",
        analysis_month=current_month,
    )
    print("Done")
