"""
ocean_proto / src / pipeline / spatial_join.py
==============================================
Módulo de cruce espacial usando celdas H3.

Versión 2: integra criterios oceanográficos multidimensionales mediante
compute_enhanced_risk_hotspots(). Mantiene compatibilidad con compute_risk_hotspots()
para backward compatibility.
"""
import h3
import geopandas as gpd
import pandas as pd
import logging
from typing import Optional
from shapely.geometry import Polygon
import json

logger = logging.getLogger(__name__)

H3_RESOLUTION = 5  # ~50 km de diámetro por celda — adecuado para datos demo en BCS


def get_h3_index(lat: float, lon: float, resolution: int) -> str:
    """Calcula el índice H3 para una coordenada."""
    return h3.latlng_to_cell(lat, lon, resolution)


def cell_to_polygon(hex_id: str) -> Polygon:
    """Convierte un índice H3 hexagonal en un polígono de Shapely."""
    boundary = h3.cell_to_boundary(hex_id)
    lng_lat_boundary = [(lng, lat) for lat, lng in boundary]
    return Polygon(lng_lat_boundary)


def compute_risk_hotspots(
    gfw_gdf: gpd.GeoDataFrame,
    obis_gdf: gpd.GeoDataFrame,
    output_path: str,
) -> Optional[gpd.GeoDataFrame]:
    """
    Cruza los datos espacialmente agrupándolos en celdas H3 y
    calcula el Collision Risk Score baseline.

    Mantiene compatibilidad con la versión original.
    """
    # Asignar celdas H3
    if not gfw_gdf.empty:
        gfw_gdf = gfw_gdf.copy()
        gfw_gdf["h3_index"] = gfw_gdf.geometry.apply(
            lambda p: get_h3_index(p.y, p.x, H3_RESOLUTION)
        )
        vessel_counts = gfw_gdf.groupby("h3_index").size().reset_index(name="vessel_count")
    else:
        vessel_counts = pd.DataFrame(columns=["h3_index", "vessel_count"])

    if not obis_gdf.empty:
        obis_gdf = obis_gdf.copy()
        obis_gdf["h3_index"] = obis_gdf.geometry.apply(
            lambda p: get_h3_index(p.y, p.x, H3_RESOLUTION)
        )
        megafauna_counts = obis_gdf.groupby("h3_index").size().reset_index(name="megafauna_count")
    else:
        megafauna_counts = pd.DataFrame(columns=["h3_index", "megafauna_count"])

    # Unir datos
    merged = pd.merge(vessel_counts, megafauna_counts, on="h3_index", how="outer").fillna(0)
    merged["vessel_count"]   = merged["vessel_count"].astype(int)
    merged["megafauna_count"] = merged["megafauna_count"].astype(int)

    # Calcular Risk Score baseline
    merged["risk_score"] = merged["vessel_count"] * merged["megafauna_count"]

    risk_hotspots = merged[merged["risk_score"] > 0].copy()
    if risk_hotspots.empty:
        risk_hotspots = merged.copy()

    if not risk_hotspots.empty:
        risk_hotspots["geometry"] = risk_hotspots["h3_index"].apply(cell_to_polygon)
        gdf_out = gpd.GeoDataFrame(risk_hotspots, geometry="geometry", crs="EPSG:4326")
    else:
        gdf_out = gpd.GeoDataFrame(
            columns=["h3_index", "vessel_count", "megafauna_count", "risk_score", "geometry"],
            crs="EPSG:4326",
        )

    gdf_out.sort_values("risk_score", ascending=False, inplace=True)
    gdf_out.reset_index(drop=True, inplace=True)
    gdf_out.to_file(output_path, driver="GeoJSON")
    return gdf_out


def compute_enhanced_risk_hotspots(
    gfw_gdf:           gpd.GeoDataFrame,
    obis_gdf:          gpd.GeoDataFrame,
    gaps_gdf:          gpd.GeoDataFrame = None,
    output_path:       str = "data/risk_hotspots.geojson",
    analysis_month:    int = None,
    use_oceanographic: bool = True,
) -> gpd.GeoDataFrame:
    """
    Versión extendida que integra los criterios oceanográficos del pipeline v2.

    Criterios integrados:
      1. Co-ocurrencia vessel × megafauna (baseline)
      2. Impacto acústico (modelo proxy por tipo de embarcación)
      3. SST (NOAA OISST via ERDDAP)
      4. Clorofila-a (MODIS Aqua via ERDDAP)
      5. Batimetría (ETOPO2022 via ERDDAP)
      6. Estacionalidad migratoria (ventanas de vulnerabilidad)
      7. Densidad de AIS Gap Events

    Parámetros
    ----------
    gfw_gdf           : GeoDataFrame con detecciones SAR de embarcaciones
    obis_gdf          : GeoDataFrame con ocurrencias de megafauna
    gaps_gdf          : GeoDataFrame con eventos de apagón AIS (opcional)
    output_path       : ruta de salida del GeoJSON
    analysis_month    : mes para el modificador temporal (1-12), None = no aplicar
    use_oceanographic : Si False, devuelve solo el baseline score

    Retorna
    -------
    GeoDataFrame con CRS y sub-scores por celda H3
    """
    # ── Paso 1: Hotspots base ─────────────────────────────────────────────────
    base_gdf = compute_risk_hotspots(gfw_gdf, obis_gdf, output_path)

    if not use_oceanographic or base_gdf is None or base_gdf.empty:
        return base_gdf

    # ── Paso 2: gfw_df con h3_index para modelo acústico ─────────────────────
    gfw_df = pd.DataFrame()
    if not gfw_gdf.empty:
        gfw_df = gfw_gdf.drop(columns="geometry", errors="ignore").copy()
        if "h3_index" not in gfw_df.columns:
            gfw_df["h3_index"] = gfw_gdf.geometry.apply(
                lambda p: get_h3_index(p.y, p.x, H3_RESOLUTION)
            )

    # ── Paso 3: Modelo acústico ────────────────────────────────────────────────
    acoustic_df = pd.DataFrame()
    if not gfw_df.empty:
        try:
            from src.pipeline.acoustic_model import compute_acoustic_risk_per_hex
            acoustic_df = compute_acoustic_risk_per_hex(gfw_df, H3_RESOLUTION)
            logger.info(f"[Enhanced] Modelo acústico: {len(acoustic_df)} celdas.")
        except Exception as e:
            logger.warning(f"[Enhanced] Modelo acústico falló: {e}")

    # ── Paso 4: Gap events por celda ──────────────────────────────────────────
    gaps_hex_df = pd.DataFrame()
    if gaps_gdf is not None and not gaps_gdf.empty:
        gaps_df = gaps_gdf.drop(columns="geometry", errors="ignore").copy()
        if "lat" in gaps_df.columns and "lon" in gaps_df.columns:
            gaps_df["h3_index"] = [
                get_h3_index(row["lat"], row["lon"], H3_RESOLUTION)
                for _, row in gaps_df.iterrows()
            ]
            gaps_hex_df = gaps_df.groupby("h3_index").size().reset_index(name="gap_count")

    # ── Paso 5: Mapa de especies por celda ────────────────────────────────────
    species_per_hex = {}
    if not obis_gdf.empty and "species" in obis_gdf.columns:
        obis_df = obis_gdf.drop(columns="geometry", errors="ignore").copy()
        if "h3_index" not in obis_df.columns:
            obis_df["h3_index"] = obis_gdf.geometry.apply(
                lambda p: get_h3_index(p.y, p.x, H3_RESOLUTION)
            )
        for hex_id, grp in obis_df.groupby("h3_index"):
            species_per_hex[hex_id] = grp["species"].unique().tolist()

    # ── Paso 6: Datos oceanográficos (ERDDAP, con caché) ─────────────────────
    sst_grid    = None
    chl_grid    = None
    bathy_grid  = None
    upwelling_df = None

    try:
        from src.pipeline.oceanographic import (
            fetch_sst_erddap,
            fetch_chlorophyll_erddap,
            fetch_bathymetry_erddap,
            compute_upwelling_index,
            aggregate_to_grid,
        )

        sst_raw = fetch_sst_erddap(use_cache=True)
        if not sst_raw.empty:
            sst_grid     = aggregate_to_grid(sst_raw, "sst", lat_col="latitude", lon_col="longitude")
            upwelling_df = compute_upwelling_index(sst_raw)

        chl_raw = fetch_chlorophyll_erddap(use_cache=True)
        if not chl_raw.empty:
            chl_grid = aggregate_to_grid(
                chl_raw, "chlorophyll_mg_m3", lat_col="latitude", lon_col="longitude"
            )

        bathy_raw = fetch_bathymetry_erddap(use_cache=True)
        if not bathy_raw.empty:
            bathy_grid = aggregate_to_grid(
                bathy_raw, "depth_m", lat_col="latitude", lon_col="longitude"
            )

    except Exception as e:
        logger.warning(f"[Enhanced] Error cargando datos oceanográficos: {e}")

    # ── Paso 7: Composite Risk Score ──────────────────────────────────────────
    hotspots_df = base_gdf.drop(columns="geometry", errors="ignore").copy()
    try:
        from src.pipeline.risk_scoring import compute_composite_risk_score
        crs_df = compute_composite_risk_score(
            hotspots_df     = hotspots_df,
            acoustic_df     = acoustic_df if not acoustic_df.empty else None,
            sst_grid        = sst_grid,
            chl_grid        = chl_grid,
            bathy_grid      = bathy_grid,
            upwelling_df    = upwelling_df,
            gaps_hex_df     = gaps_hex_df if not gaps_hex_df.empty else None,
            species_per_hex = species_per_hex,
            analysis_month  = analysis_month,
        )
    except Exception as e:
        logger.warning(f"[Enhanced] Composite risk score falló: {e}. Usando baseline.")
        crs_df = hotspots_df.copy()
        crs_df["crs"]       = crs_df["risk_score"]
        crs_df["crs_100"]   = crs_df["risk_score"]
        crs_df["crs_level"] = "MEDIUM"

    # ── Paso 8: Reconstruir GeoDataFrame con geometrías H3 ───────────────────
    if not crs_df.empty:
        crs_df["geometry"] = crs_df["h3_index"].apply(cell_to_polygon)
        gdf_out = gpd.GeoDataFrame(crs_df, geometry="geometry", crs="EPSG:4326")
        gdf_out.sort_values("crs_100", ascending=False, inplace=True)
        gdf_out.reset_index(drop=True, inplace=True)
        gdf_out.to_file(output_path, driver="GeoJSON")
        logger.info(
            f"[Enhanced] GeoJSON exportado con CRS: {len(gdf_out)} celdas → {output_path}"
        )
        return gdf_out

    return base_gdf


if __name__ == "__main__":
    import logging as _log
    _log.basicConfig(level=_log.INFO)
    from src.pipeline.ingest import run_ingestion
    from datetime import datetime

    print("Ingesting data...")
    gfw, obis, _platforms, _support, gaps = run_ingestion("data/obis_data.csv")
    print("Processing enhanced spatial join with oceanographic criteria...")
    current_month = datetime.now().month
    compute_enhanced_risk_hotspots(
        gfw, obis, gaps_gdf=gaps,
        output_path="data/risk_hotspots.geojson",
        analysis_month=current_month,
    )
    print("Done")
