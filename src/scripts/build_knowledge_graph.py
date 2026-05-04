#!/usr/bin/env python3
"""
ocean_proto / src / scripts / build_knowledge_graph.py
======================================================
Script standalone para construir el Knowledge Graph oceánico
y volcar los artefactos en data/knowledge_graph/.

Uso:
    python -m src.scripts.build_knowledge_graph [--no-enrich]

Flags:
    --no-enrich   Omite las llamadas a GFW Identity e IUCN
                  (útil para pruebas offline o cuando no hay API keys).
"""

import sys
import os
import logging
import argparse
import pandas as pd
import geopandas as gpd

# Asegurar que el root del proyecto esté en el path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.pipeline.ingest import run_ingestion
from src.pipeline.knowledge_graph import build_and_export


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("build_kg")

    parser = argparse.ArgumentParser(description="Construye el OceanProto Knowledge Graph")
    parser.add_argument("--no-enrich", action="store_true",
                        help="Omite enriquecimiento externo (GFW Identity + IUCN)")
    parser.add_argument("--out-dir", default="data/knowledge_graph",
                        help="Directorio de salida (default: data/knowledge_graph)")
    args = parser.parse_args()

    do_enrich = not args.no_enrich

    logger.info("━━━ OceanProto Knowledge Graph Builder ━━━")
    logger.info(f"Enriquecimiento externo: {'Activado' if do_enrich else 'Desactivado'}")

    # ── 1. Ingesta de datos ──────────────────────────────────────────────────
    logger.info("Fase 1/4 — Ingesta de datos (GFW + OBIS + O&G + OSVs + Gaps AIS)...")
    gfw_gdf, obis_gdf, platforms_gdf, support_gdf, gaps_gdf = run_ingestion("data/obis_data.csv")

    gfw_df       = pd.DataFrame(gfw_gdf.drop(columns="geometry", errors="ignore"))
    obis_df      = pd.DataFrame(obis_gdf.drop(columns="geometry", errors="ignore"))
    platforms_df = pd.DataFrame(platforms_gdf.drop(columns="geometry", errors="ignore"))
    support_df   = pd.DataFrame(support_gdf.drop(columns="geometry", errors="ignore"))
    gaps_df      = pd.DataFrame(gaps_gdf.drop(columns="geometry", errors="ignore"))

    logger.info(f"  GFW SAR   : {len(gfw_df)} registros")
    logger.info(f"  OBIS      : {len(obis_df)} registros")
    logger.info(f"  Platforms : {len(platforms_df)} plataformas O&G")
    logger.info(f"  OSVs      : {len(support_df)} buques de apoyo")
    logger.info(f"  Gaps AIS  : {len(gaps_df)} apagones")

    # ── 2. Cargar hotspots (si ya existen del pipeline anterior) ─────────────
    hotspots_df = None
    hotspot_path = "data/risk_hotspots.geojson"
    if os.path.exists(hotspot_path):
        logger.info("Fase 2/4 — Cargando hotspots existentes...")
        gdf = gpd.read_file(hotspot_path)
        hotspots_df = pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))
        logger.info(f"  Hotspots cargados: {len(hotspots_df)} celdas H3")
    else:
        logger.info("Fase 2/4 — No existen hotspots previos; los HexCell serán inferidos de eventos.")

    # ── 3. Construir y exportar el Knowledge Graph ────────────────────────────
    logger.info("Fase 3/4 — Construyendo Knowledge Graph v3...")
    G = build_and_export(
        gfw_df,
        obis_df,
        platforms_df=platforms_df,
        support_df=support_df,
        gaps_df=gaps_df,
        hotspots_df=hotspots_df,
        enrich_vessels=do_enrich,
        enrich_iucn=do_enrich,
        out_dir=args.out_dir,
    )

    # ── 4. Resumen ────────────────────────────────────────────────────────────
    logger.info("Fase 4/4 — Resumen final")
    print("\n" + "═" * 55)
    print("  ✓  OceanProto Knowledge Graph construido")
    print("═" * 55)
    print(f"  Nodos totales    : {G.number_of_nodes():>6}")
    print(f"  Aristas totales  : {G.number_of_edges():>6}")
    print()

    node_types: dict[str, int] = {}
    for _, d in G.nodes(data=True):
        t = d.get("type", "Unknown")
        node_types[t] = node_types.get(t, 0) + 1
    for t, cnt in sorted(node_types.items()):
        print(f"  {t:<28}: {cnt}")

    print()
    print(f"  Artefactos en: {args.out_dir}/")
    print("    ├── graph.json            ← Graphify compatible")
    print("    ├── GRAPH_REPORT.md       ← Auditoría del grafo")
    print("    ├── graph.cypher          ← Import Neo4j")
    print("    └── graph_hexcells.geojson← Leaflet / QGIS")
    print("═" * 55)
    print()
    print("  Consulta el grafo con Graphify:")
    print('    /graphify query "especies en zonas de alto riesgo"')
    print('    /graphify path VesselEvent Species')
    print('    /graphify explain RiskZone')
    print()


if __name__ == "__main__":
    main()
