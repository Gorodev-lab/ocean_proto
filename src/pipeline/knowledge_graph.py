"""
ocean_proto / src / pipeline / knowledge_graph.py
=================================================
Pipeline de construcción del Knowledge Graph oceánico.

Entidades (nodos):
  - HexCell             : celda H3 resolución 7
  - VesselEvent         : detección SAR de embarcación (GFW)
  - VesselIdentity      : identidad permanente del barco (nombre, bandera, IMO)
  - MegafaunaOccurrence : avistamiento puntual (OBIS)
  - Species             : especie marina (con estado IUCN)
  - WhaleSpecies        : sub-clase Species para cetáceos relevantes a O&G
  - OilPlatform         : plataforma offshore de petróleo/gas (GFW/BOEM)
  - SupportVessel       : buque de apoyo O&G (OSV/PSV/AHTS — GFW)
  - AisGapEvent         : apagón de transpondedor AIS en the mar (GFW)
  - RiskZone            : agregado de celdas H3 de alto riesgo

Relaciones (aristas):
  - DETECTED_IN         : VesselEvent    → HexCell
  - OBSERVED_IN         : MegafaunaOccurrence → HexCell
  - IS_CLASS            : VesselEvent    → VesselIdentity
  - HAS_OCCURRENCE      : Species        → MegafaunaOccurrence
  - BORDERS             : HexCell        → HexCell  (vecinos k=1)
  - PART_OF             : HexCell        → RiskZone
  - OVERLAPS_HABITAT    : RiskZone       → Species
  - LOCATED_IN          : OilPlatform    → HexCell
  - NEAR_WHALE_HABITAT  : OilPlatform    → WhaleSpecies  (coexistencia en hex)
  - OPERATES_IN         : SupportVessel  → HexCell       (posición OSV)
  - SERVES_PLATFORM     : SupportVessel  → OilPlatform   (hex compartido)
  - WENT_DARK_IN        : AisGapEvent    → HexCell       (ubicación del gap)
  - DARK_NEAR_WHALE     : AisGapEvent    → WhaleSpecies  (gap en hábitat cetaceo)
  - VESSEL_HAD_GAP      : AisGapEvent    → SupportVessel (asociación MMSI)
"""

import os
import json
import logging
import hashlib
import time
import pandas as pd
import networkx as nx
import h3
from shapely.geometry import Polygon
from dotenv import load_dotenv
from typing import Optional
from src.pipeline._resilience import http_get

load_dotenv()
logger = logging.getLogger(__name__)

# ── Configuración ────────────────────────────────────────────────────────────
H3_RESOLUTION   = 7
RISK_THRESHOLD  = 5          # risk_score mínimo para declarar RiskZone
GFW_API_TOKEN   = os.environ.get("GFW_API_TOKEN", "")
GFW_VESSEL_URL  = "https://gateway.api.globalfishingwatch.org/v3/vessels"
IUCN_API_KEY     = os.environ.get("IUCN_API_KEY", "")   # gratis en iucnredlist.org
# API v4 (recomendada): https://api.iucnredlist.org/api-docs/index.html
IUCN_V4_BASE     = "https://api.iucnredlist.org"
# API v3 (fallback):    https://apiv3.iucnredlist.org
IUCN_V3_BASE     = "https://apiv3.iucnredlist.org/api/v3/species"
GRAPH_OUT_DIR    = "data/knowledge_graph"

# ── Helpers de enriquecimiento ────────────────────────────────────────────────

_iucn_cache: dict[str, str] = {}

def _iucn_status(species_name: str) -> str:
    """
    Consulta el estado IUCN Red List de una especie.
    Usa http_get con retry automático. Fallback v4 → v3.
    """
    if species_name in _iucn_cache:
        return _iucn_cache[species_name]
    if not IUCN_API_KEY:
        return "Unknown"

    encoded = species_name.replace(" ", "%20")

    # Intento v4
    data = http_get(
        f"{IUCN_V4_BASE}/api/v4/taxa/scientific_name/{encoded}",
        token=IUCN_API_KEY,
        timeout=12,
    )
    if data:
        assessments = data.get("assessments", [])
        if assessments:
            code = assessments[0].get("red_list_category", {}).get("code", "Unknown")
            _iucn_cache[species_name] = code
            return code

    # Fallback v3
    data = http_get(
        f"{IUCN_V3_BASE}/{species_name}",
        params={"token": IUCN_API_KEY},
        timeout=12,
    )
    if data:
        result = data.get("result", [])
        if result:
            status = result[0].get("category", "Unknown")
            _iucn_cache[species_name] = status
            return status

    _iucn_cache[species_name] = "Unknown"
    return "Unknown"


_vessel_cache: dict[str, dict] = {}

def _enrich_vessel(mmsi: str) -> dict:
    """
    Enriquece una detección SAR con datos de identidad GFW.
    Usa http_get con retry automático.
    """
    if mmsi in _vessel_cache:
        return _vessel_cache[mmsi]
    if not GFW_API_TOKEN or mmsi == "unknown":
        return {}

    data = http_get(
        f"{GFW_VESSEL_URL}/search",
        params={"datasets": "public-global-vessel-identity:latest", "query": mmsi, "limit": 1},
        token=GFW_API_TOKEN,
        timeout=12,
    )
    info: dict = {}
    if data:
        entries = data.get("entries", [])
        if entries:
            e = entries[0]
            info = {
                "vessel_name":    e.get("shipname", ""),
                "flag":           e.get("flag", ""),
                "imo":            str(e.get("imo", "")),
                "vessel_type_gfw": e.get("vesselType", ""),
            }
    _vessel_cache[mmsi] = info
    return info


# ── Construcción del grafo ────────────────────────────────────────────────────

def build_knowledge_graph(
    gfw_df:        pd.DataFrame,
    obis_df:       pd.DataFrame,
    platforms_df:  pd.DataFrame | None = None,
    support_df:    pd.DataFrame | None = None,
    gaps_df:       pd.DataFrame | None = None,
    hotspots_df:   pd.DataFrame | None = None,
    enrich_vessels: bool = True,
    enrich_iucn:    bool = True,
) -> nx.MultiDiGraph:
    """
    Ensambla el MultiDiGraph combinando GFW + OBIS + OilPlatforms +
    SupportVessels + AIS Gaps + enriquecimiento.

    Parámetros
    ----------
    gfw_df        : DataFrame [mmsi, timestamp, lat, lon, vessel_type]
    obis_df       : DataFrame [species, decimalLatitude, decimalLongitude, eventDate]
    platforms_df  : DataFrame [platform_id, lat, lon, category, label, ...]
    support_df    : DataFrame [vessel_id, mmsi, shipname, flag, lat, lon, ...]
    gaps_df       : DataFrame [gap_id, vessel_id, mmsi, lat, lon, gap_hours, ...]
    hotspots_df   : DataFrame [h3_index, vessel_count, megafauna_count, risk_score]
    enrich_vessels: si True, consulta GFW Identity por cada MMSI único
    enrich_iucn   : si True, consulta IUCN por cada especie única
    """
    G = nx.MultiDiGraph()
    G.graph["name"]    = "OceanProto Knowledge Graph"
    G.graph["created"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    G.graph["version"] = "3.0"   # v3: SupportVessels + AIS Gaps

    logger.info("═══ Construyendo Knowledge Graph oceánico (v3: O&G + OSVs + Gaps AIS) ═══")

    # ── 0. Nodos OilPlatform ──────────────────────────────────────────
    platform_hexes: set[str] = set()   # para cruzar con ballenas después

    if platforms_df is not None and not platforms_df.empty:
        plat_count = 0
        for _, row in platforms_df.iterrows():
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except (ValueError, KeyError):
                continue

            hid    = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
            plat_id = f"plat_{row.get('platform_id', '') or f'{lat:.4f}_{lon:.4f}'}"

            # Asegurar que el HexCell existe
            if hid not in G:
                G.add_node(hid, type="HexCell", h3_index=hid,
                           risk_score=0, vessel_count=0, megafauna_count=0)
            platform_hexes.add(hid)

            G.add_node(
                plat_id,
                type="OilPlatform",
                platform_id=str(row.get("platform_id", "")),
                lat=lat,
                lon=lon,
                category=str(row.get("category", "OIL")),
                label=str(row.get("label", "")),
                sub_category=str(row.get("sub_category", "")),
                first_timestamp=str(row.get("first_timestamp", "")),
                last_timestamp=str(row.get("last_timestamp", "")),
                source=str(row.get("source", "GFW_infrastructure")),
            )
            # Arista OilPlatform → HexCell
            G.add_edge(plat_id, hid, relation="LOCATED_IN")
            plat_count += 1

        logger.info(f"  + {plat_count} nodos OilPlatform agregados")
    else:
        logger.info("  ! platforms_df vacío — sin nodos OilPlatform")

    # ── 1. Nodos HexCell desde hotspots_df ──────────────────────────────────
    if hotspots_df is not None and not hotspots_df.empty:
        for row in hotspots_df.itertuples(index=False):
            hid = str(row.h3_index)
            G.add_node(
                hid,
                type="HexCell",
                h3_index=hid,
                risk_score=int(getattr(row, 'risk_score', 0) or 0),
                vessel_count=int(getattr(row, 'vessel_count', 0) or 0),
                megafauna_count=int(getattr(row, 'megafauna_count', 0) or 0),
            )
        logger.info("  + %d nodos HexCell agregados", len(hotspots_df))
    else:
        logger.info("  ! hotspots_df vacío — los HexCell se crearán desde eventos")

    # ── 2. Nodos VesselEvent + VesselIdentity ────────────────────────────────
    unique_mmsi = gfw_df["mmsi"].unique() if not gfw_df.empty else []
    vessel_identities: dict[str, dict] = {}

    if enrich_vessels and len(unique_mmsi) > 0:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        logger.info("  Enriqueciendo %d MMSI únicos contra GFW Identity (batch concurrente)...", len(unique_mmsi))
        # Cap at 20 workers — respeta el rate limit de GFW
        max_workers = min(20, len(unique_mmsi))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_enrich_vessel, str(m)): str(m) for m in unique_mmsi}
            for fut in as_completed(futures):
                mmsi_key = futures[fut]
                try:
                    vessel_identities[mmsi_key] = fut.result()
                except Exception as exc:
                    logger.warning("MMSI %s enrichment falló: %s", mmsi_key, exc)
                    vessel_identities[mmsi_key] = {}

    vessel_event_count = 0
    for idx, row in gfw_df.iterrows():
        try:
            mmsi = str(row.get("mmsi", "unknown"))
            lat  = float(row["lat"])
            lon  = float(row["lon"])
        except (ValueError, KeyError):
            continue

        # Determinar celda H3
        hid = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)

        # Crear HexCell si aún no existe
        if hid not in G:
            G.add_node(hid, type="HexCell", h3_index=hid,
                       risk_score=0, vessel_count=0, megafauna_count=0)

        # ID único del evento
        raw_ts  = str(row.get("timestamp", idx))
        evt_id  = f"ve_{mmsi}_{hashlib.md5(raw_ts.encode()).hexdigest()[:8]}"

        identity = vessel_identities.get(mmsi, {})
        G.add_node(
            evt_id,
            type="VesselEvent",
            mmsi=mmsi,
            timestamp=raw_ts,
            lat=lat,
            lon=lon,
            vessel_type=str(row.get("vessel_type", "unknown")),
            vessel_name=identity.get("vessel_name", ""),
            flag=identity.get("flag", ""),
            imo=identity.get("imo", ""),
            vessel_type_gfw=identity.get("vessel_type_gfw", ""),
        )

        # Arista VesselEvent → HexCell
        G.add_edge(evt_id, hid, relation="DETECTED_IN")

        # Nodo VesselIdentity (por MMSI, una sola vez)
        vi_id = f"vi_{mmsi}"
        if vi_id not in G:
            G.add_node(
                vi_id,
                type="VesselIdentity",
                mmsi=mmsi,
                **identity,
            )
        G.add_edge(evt_id, vi_id, relation="IS_CLASS")

        vessel_event_count += 1

    logger.info(f"  + {vessel_event_count} nodos VesselEvent agregados")

    # ── 3. Nodos Species + MegafaunaOccurrence ───────────────────────────────
    unique_species = obis_df["species"].unique() if not obis_df.empty else []
    iucn_statuses: dict[str, str] = {}

    if enrich_iucn:
        logger.info(f"  Consultando IUCN para {len(unique_species)} especies...")
        for sp in unique_species:
            iucn_statuses[sp] = _iucn_status(sp)

    # Determinar qué especies son cetáceos relevantes a O&G
    oil_relevant_species: set[str] = set()
    if not obis_df.empty and "oil_relevant" in obis_df.columns:
        oil_relevant_species = set(
            obis_df.loc[obis_df.oil_relevant == True, "species"].unique()
        )

    # Nodos Species (deduplicados) — WhaleSpecies si es cetáceo O&G
    for sp in unique_species:
        sp_id    = f"sp_{sp.replace(' ', '_')}"
        is_whale = sp in oil_relevant_species
        G.add_node(
            sp_id,
            type="WhaleSpecies" if is_whale else "Species",
            scientificName=sp,
            iucn_status=iucn_statuses.get(sp, "Unknown"),
            oil_relevant=is_whale,
            taxa_group="Cetacea" if is_whale else "Marine",
        )

    occ_count = 0
    for idx, row in obis_df.iterrows():
        try:
            lat = float(row["decimalLatitude"])
            lon = float(row["decimalLongitude"])
            sp  = str(row.get("species", "Unknown"))
        except (ValueError, KeyError):
            continue

        hid    = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
        occ_id = f"occ_{sp.replace(' ', '_')}_{idx}"
        sp_id  = f"sp_{sp.replace(' ', '_')}"

        if hid not in G:
            G.add_node(hid, type="HexCell", h3_index=hid,
                       risk_score=0, vessel_count=0, megafauna_count=0)

        G.add_node(
            occ_id,
            type="MegafaunaOccurrence",
            species=sp,
            lat=lat,
            lon=lon,
            eventDate=str(row.get("eventDate", "")),
            datasetName=str(row.get("datasetName", "OBIS")),
        )

        # Aristas
        G.add_edge(occ_id, hid,    relation="OBSERVED_IN")
        G.add_edge(sp_id,  occ_id, relation="HAS_OCCURRENCE")

        occ_count += 1

    logger.info(f"  + {occ_count} nodos MegafaunaOccurrence agregados")

    # ── 4*. Aristas NEAR_WHALE_HABITAT: OilPlatform → WhaleSpecies ─────────
    # Una plataforma está "cerca" de hábitat de ballena si comparte HexCell
    # o está en un anillo k=2 alrededor de un hex con avistamientos
    whale_hex_to_species: dict[str, list[str]] = {}
    for occ_id, d in G.nodes(data=True):
        if d.get("type") != "MegafaunaOccurrence":
            continue
        sp = d.get("species", "")
        sp_id = f"sp_{sp.replace(' ', '_')}"
        if G.nodes.get(sp_id, {}).get("type") != "WhaleSpecies":
            continue
        occ_hex = h3.latlng_to_cell(d["lat"], d["lon"], H3_RESOLUTION)
        whale_hex_to_species.setdefault(occ_hex, []).append(sp_id)
        # También incluir vecinos k=1 para proximidad
        for nb in h3.grid_disk(occ_hex, 1):
            whale_hex_to_species.setdefault(nb, []).append(sp_id)

    near_habitat_edges = 0
    for plat_node, plat_data in G.nodes(data=True):
        if plat_data.get("type") != "OilPlatform":
            continue
        plat_lat = plat_data.get("lat")
        plat_lon = plat_data.get("lon")
        if plat_lat is None or plat_lon is None:
            continue
        plat_hex = h3.latlng_to_cell(float(plat_lat), float(plat_lon), H3_RESOLUTION)
        species_nearby = set(whale_hex_to_species.get(plat_hex, []))
        for sp_id in species_nearby:
            G.add_edge(plat_node, sp_id, relation="NEAR_WHALE_HABITAT")
            near_habitat_edges += 1

    logger.info(f"  + {near_habitat_edges} aristas NEAR_WHALE_HABITAT agregadas")

    # ── 4a. Nodos SupportVessel + OPERATES_IN + SERVES_PLATFORM ──────
    # Indice inverso hex → lista de platform_ids (para SERVES_PLATFORM)
    platform_hex_to_id: dict[str, list[str]] = {}
    for n, d in G.nodes(data=True):
        if d.get("type") == "OilPlatform":
            lat = d.get("lat")
            lon = d.get("lon")
            if lat is not None and lon is not None:
                hid = h3.latlng_to_cell(float(lat), float(lon), H3_RESOLUTION)
                platform_hex_to_id.setdefault(hid, []).append(n)

    sv_count = 0
    sv_serves = 0
    if support_df is not None and not support_df.empty:
        for _, row in support_df.iterrows():
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except (ValueError, KeyError, TypeError):
                continue

            hid   = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
            sv_id = f"osv_{row.get('vessel_id') or row.get('mmsi') or f'{lat:.4f}_{lon:.4f}'}"

            if hid not in G:
                G.add_node(hid, type="HexCell", h3_index=hid,
                           risk_score=0, vessel_count=0, megafauna_count=0)

            G.add_node(
                sv_id,
                type="SupportVessel",
                vessel_id=str(row.get("vessel_id", "")),
                mmsi=str(row.get("mmsi", "")),
                imo=str(row.get("imo", "")),
                shipname=str(row.get("shipname", "")),
                flag=str(row.get("flag", "")),
                vessel_type=str(row.get("vessel_type", "support")),
                gear_type=str(row.get("gear_type", "")),
                lat=lat,
                lon=lon,
                length_m=row.get("length_m", None),
                tonnage_gt=row.get("tonnage_gt", None),
                source=str(row.get("source", "GFW_support_vessels")),
            )
            G.add_edge(sv_id, hid, relation="OPERATES_IN")
            sv_count += 1

            # Conectar OSV con plataformas en el mismo hex o vecinos k=1
            candidate_hexes = {hid} | set(h3.grid_disk(hid, 1))
            for chex in candidate_hexes:
                for plat_id in platform_hex_to_id.get(chex, []):
                    G.add_edge(sv_id, plat_id, relation="SERVES_PLATFORM")
                    sv_serves += 1

    logger.info(
        f"  + {sv_count} nodos SupportVessel | {sv_serves} aristas SERVES_PLATFORM"
    )

    # ── 4b. Nodos AisGapEvent + WENT_DARK_IN + DARK_NEAR_WHALE + VESSEL_HAD_GAP ──
    # Mapa MMSI → node SupportVessel (para VESSEL_HAD_GAP)
    mmsi_to_sv: dict[str, str] = {
        d.get("mmsi", ""): n
        for n, d in G.nodes(data=True)
        if d.get("type") == "SupportVessel" and d.get("mmsi", "")
    }

    gap_count = 0
    dark_whale_edges = 0
    if gaps_df is not None and not gaps_df.empty:
        for _, row in gaps_df.iterrows():
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except (ValueError, KeyError, TypeError):
                continue

            hid    = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
            gap_id = f"gap_{row.get('gap_id') or f'{lat:.4f}_{lon:.4f}_{row.get("start","")}'}"

            if hid not in G:
                G.add_node(hid, type="HexCell", h3_index=hid,
                           risk_score=0, vessel_count=0, megafauna_count=0)

            G.add_node(
                gap_id,
                type="AisGapEvent",
                gap_id=str(row.get("gap_id", "")),
                vessel_id=str(row.get("vessel_id", "")),
                mmsi=str(row.get("mmsi", "")),
                shipname=str(row.get("shipname", "")),
                flag=str(row.get("flag", "")),
                lat=lat,
                lon=lon,
                start=str(row.get("start", "")),
                end=str(row.get("end", "")),
                gap_hours=float(row.get("gap_hours", 0)),
                source="GFW_gaps",
            )
            G.add_edge(gap_id, hid, relation="WENT_DARK_IN")
            gap_count += 1

            # Cruzar con hábitat de ballenas (hex + k=1)
            candidate_hexes = {hid} | set(h3.grid_disk(hid, 1))
            for chex in candidate_hexes:
                for sp_id in whale_hex_to_species.get(chex, []):
                    G.add_edge(gap_id, sp_id, relation="DARK_NEAR_WHALE")
                    dark_whale_edges += 1

            # Conectar con SupportVessel si el MMSI coincide
            mmsi = str(row.get("mmsi", ""))
            if mmsi and mmsi in mmsi_to_sv:
                G.add_edge(gap_id, mmsi_to_sv[mmsi], relation="VESSEL_HAD_GAP")

    logger.info(
        f"  + {gap_count} nodos AisGapEvent | "
        f"{dark_whale_edges} aristas DARK_NEAR_WHALE"
    )

    # ── 4. Aristas BORDERS (vecinos H3 k=1) ─────────────────────────────────
    hex_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "HexCell"]
    border_edges = 0
    for hid in hex_nodes:
        neighbors = set(h3.grid_disk(hid, 1)) - {hid}
        for nb in neighbors:
            if nb in G:
                G.add_edge(hid, nb, relation="BORDERS")
                border_edges += 1
    logger.info(f"  + {border_edges} aristas BORDERS agregadas")

    # ── 5. Nodos RiskZone + aristas PART_OF + OVERLAPS_HABITAT ──────────────
    high_risk = [
        (n, d) for n, d in G.nodes(data=True)
        if d.get("type") == "HexCell" and d.get("risk_score", 0) >= RISK_THRESHOLD
    ]
    if high_risk:
        rz_id = "rz_primary"
        G.add_node(
            rz_id,
            type="RiskZone",
            zone_id="primary",
            severity="HIGH",
            cell_count=len(high_risk),
            max_risk_score=max(d["risk_score"] for _, d in high_risk),
        )
        for hid, _ in high_risk:
            G.add_edge(hid, rz_id, relation="PART_OF")

        # Vincular especies que aparecen en esas celdas a la RiskZone
        at_risk_species: set[str] = set()
        for occ_id, d in G.nodes(data=True):
            if d.get("type") != "MegafaunaOccurrence":
                continue
            occ_hex = h3.latlng_to_cell(d["lat"], d["lon"], H3_RESOLUTION)
            if occ_hex in {hid for hid, _ in high_risk}:
                # Encontrar su Species padre
                for pred in G.predecessors(occ_id):
                    if G.nodes[pred].get("type") == "Species":
                        at_risk_species.add(pred)

        for sp_id in at_risk_species:
            G.add_edge(rz_id, sp_id, relation="OVERLAPS_HABITAT")

        logger.info(f"  + RiskZone con {len(high_risk)} celdas y "
                    f"{len(at_risk_species)} especies en riesgo")

    logger.info(f"═══ Grafo final: {G.number_of_nodes()} nodos, "
                f"{G.number_of_edges()} aristas ═══")
    return G


# ── Exportación ───────────────────────────────────────────────────────────────

def export_graph_json(G: nx.MultiDiGraph, out_dir: str = GRAPH_OUT_DIR) -> str:
    """Exporta el grafo en formato graph.json compatible con Graphify."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "graph.json")
    data = nx.node_link_data(G, edges="links")
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"  graph.json exportado → {path}")
    return path


def export_graph_report(G: nx.MultiDiGraph, out_dir: str = GRAPH_OUT_DIR) -> str:
    """Genera un GRAPH_REPORT.md inspirado en el formato de Graphify."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "GRAPH_REPORT.md")

    # God nodes: mayor grado total
    degree_sorted = sorted(G.degree(), key=lambda x: x[1], reverse=True)[:10]

    # Sorpresas: aristas entre tipos de nodos poco esperados
    surprises = []
    for u, v, d in G.edges(data=True):
        t_u = G.nodes[u].get("type", "?")
        t_v = G.nodes[v].get("type", "?")
        rel = d.get("relation", "?")
        if (t_u, rel, t_v) in [("VesselIdentity", "IS_CLASS", "VesselEvent"),
                                 ("RiskZone", "OVERLAPS_HABITAT", "Species")]:
            surprises.append((u, rel, v))

    # Estadísticas por tipo
    type_counts: dict[str, int] = {}
    for _, d in G.nodes(data=True):
        t = d.get("type", "Unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    with open(path, "w") as f:
        f.write(f"# OceanProto — Knowledge Graph Report\n\n")
        f.write(f"**Generado:** {G.graph.get('created', '')}\n\n")
        f.write(f"| Métrica | Valor |\n|---|---|\n")
        f.write(f"| Nodos totales | {G.number_of_nodes()} |\n")
        f.write(f"| Aristas totales | {G.number_of_edges()} |\n")
        for t, cnt in type_counts.items():
            f.write(f"| Nodos `{t}` | {cnt} |\n")
        f.write("\n## God Nodes (mayor conectividad)\n\n")
        for node, deg in degree_sorted:
            t = G.nodes[node].get("type", "?")
            f.write(f"- `{node}` ({t}) — grado {deg}\n")
        f.write("\n## Aristas Sorprendentes\n\n")
        for u, rel, v in surprises[:20]:
            f.write(f"- `{u}` —[{rel}]→ `{v}`\n")
        f.write("\n## Preguntas sugeridas para el AI assistant\n\n")
        f.write("- `/graphify query \"¿qué especies están en la zona de mayor riesgo?\"`\n")
        f.write("- `/graphify query \"¿qué buques se detectaron en celdas H3 con megafauna?\"`\n")
        f.write("- `/graphify path VesselEvent Species`\n")
        f.write("- `/graphify explain RiskZone`\n")

    logger.info(f"  GRAPH_REPORT.md exportado → {path}")
    return path


def export_cypher(G: nx.MultiDiGraph, out_dir: str = GRAPH_OUT_DIR) -> str:
    """Exporta sentencias Cypher para importar el grafo en Neo4j."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "graph.cypher")
    lines: list[str] = ["// OceanProto Knowledge Graph — Neo4j Cypher Import\n"]

    # MERGE de nodos
    for node_id, attrs in G.nodes(data=True):
        ntype = attrs.get("type", "Node")
        props = {k: v for k, v in attrs.items() if k != "type" and v != ""}
        props_str = ", ".join(
            f"{k}: {json.dumps(str(v))}" for k, v in props.items()
        )
        safe_id = str(node_id).replace("'", "\\'")
        lines.append(f"MERGE (:{ntype} {{id: '{safe_id}', {props_str}}});")

    lines.append("")

    # MERGE de relaciones
    for u, v, data in G.edges(data=True):
        rel = data.get("relation", "RELATED")
        su  = str(u).replace("'", "\\'")
        sv  = str(v).replace("'", "\\'")
        lines.append(
            f"MATCH (a {{id:'{su}'}}), (b {{id:'{sv}'}}) "
            f"MERGE (a)-[:{rel}]->(b);"
        )

    with open(path, "w") as f:
        f.write("\n".join(lines))

    logger.info(f"  graph.cypher exportado → {path}")
    return path


def export_geojson_graph(G: nx.MultiDiGraph, out_dir: str = GRAPH_OUT_DIR) -> str:
    """
    Exporta un GeoJSON con los nodos HexCell enriquecidos con su tipo de nodo y
    polígono H3 — listo para Leaflet o QGIS.
    """
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "graph_hexcells.geojson")

    features = []
    for node_id, attrs in G.nodes(data=True):
        if attrs.get("type") != "HexCell":
            continue
        try:
            boundary = h3.cell_to_boundary(str(node_id))
            coords   = [[lng, lat] for lat, lng in boundary]
            coords.append(coords[0])  # cerrar polígono
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {k: v for k, v in attrs.items()},
            })
        except Exception:
            continue

    fc = {"type": "FeatureCollection", "features": features}
    with open(path, "w") as f:
        json.dump(fc, f, indent=2)

    logger.info(f"  graph_hexcells.geojson exportado → {path}")
    return path


# ── Entry point ───────────────────────────────────────────────────────────────

def build_and_export(
    gfw_df:        pd.DataFrame,
    obis_df:       pd.DataFrame,
    platforms_df:  pd.DataFrame | None = None,
    support_df:    pd.DataFrame | None = None,
    gaps_df:       pd.DataFrame | None = None,
    hotspots_df:   pd.DataFrame | None = None,
    enrich_vessels: bool = True,
    enrich_iucn:    bool = True,
    out_dir: str = GRAPH_OUT_DIR,
) -> nx.MultiDiGraph:
    """Construye y exporta el Knowledge Graph en todos los formatos."""
    G = build_knowledge_graph(
        gfw_df, obis_df,
        platforms_df=platforms_df,
        support_df=support_df,
        gaps_df=gaps_df,
        hotspots_df=hotspots_df,
        enrich_vessels=enrich_vessels,
        enrich_iucn=enrich_iucn,
    )
    export_graph_json(G, out_dir)
    export_graph_report(G, out_dir)
    export_cypher(G, out_dir)
    export_geojson_graph(G, out_dir)
    return G


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    from src.pipeline.ingest import run_ingestion
    from src.pipeline.spatial_join import compute_risk_hotspots
    import tempfile

    gfw_gdf, obis_gdf, platforms_gdf, support_gdf, gaps_gdf = run_ingestion("data/obis_data.csv")

    gfw_df       = pd.DataFrame(gfw_gdf.drop(columns="geometry", errors="ignore"))
    obis_df      = pd.DataFrame(obis_gdf.drop(columns="geometry", errors="ignore"))
    platforms_df = pd.DataFrame(platforms_gdf.drop(columns="geometry", errors="ignore"))
    support_df   = pd.DataFrame(support_gdf.drop(columns="geometry", errors="ignore"))
    gaps_df      = pd.DataFrame(gaps_gdf.drop(columns="geometry", errors="ignore"))

    # Cargar hotspots existentes si los hay
    hotspots_df = None
    if os.path.exists("data/risk_hotspots.geojson"):
        import geopandas as gpd
        gdf = gpd.read_file("data/risk_hotspots.geojson")
        hotspots_df = pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))

    G = build_and_export(
        gfw_df, obis_df,
        platforms_df=platforms_df,
        support_df=support_df,
        gaps_df=gaps_df,
        hotspots_df=hotspots_df,
    )
    print(f"\n✓ Knowledge Graph v3 listo en data/knowledge_graph/")
    print(f"  Nodos : {G.number_of_nodes()}")
    print(f"  Aristas: {G.number_of_edges()}")
