"""
ocean_proto / tests / test_pipeline.py
=======================================
Pruebas unitarias mínimas para el pipeline de ingesta,
spatial join y knowledge graph.
"""

import os
import sys
import json
import pytest
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# Asegurar que el root del proyecto esté en el path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_gfw_df():
    """DataFrame simulando detecciones SAR de GFW."""
    return pd.DataFrame({
        "mmsi": ["123456789", "987654321", "123456789", "111222333"],
        "timestamp": [
            "2024-01-15T10:00:00Z",
            "2024-01-15T11:00:00Z",
            "2024-02-20T09:00:00Z",
            "2024-03-01T14:00:00Z",
        ],
        "lat": [26.5, 27.0, 26.5, 28.0],
        "lon": [-112.0, -111.5, -112.0, -110.0],
        "vessel_type": ["fishing", "tanker", "fishing", "cargo"],
    })


@pytest.fixture
def mock_obis_df():
    """DataFrame simulando avistamientos de megafauna (OBIS)."""
    return pd.DataFrame({
        "species": [
            "Balaenoptera musculus",
            "Megaptera novaeangliae",
            "Balaenoptera musculus",
            "Rhincodon typus",
            "Eschrichtius robustus",
        ],
        "decimalLatitude": [26.5, 27.0, 26.5, 25.0, 28.0],
        "decimalLongitude": [-112.0, -111.5, -112.1, -109.0, -110.0],
        "eventDate": [
            "2024-01-10",
            "2024-02-15",
            "2024-03-20",
            "2024-04-01",
            "2024-05-10",
        ],
        "datasetName": ["OBIS"] * 5,
    })


@pytest.fixture
def mock_platforms_df():
    """DataFrame simulando plataformas O&G."""
    return pd.DataFrame({
        "platform_id": ["P001", "P002"],
        "lat": [26.5, 27.0],
        "lon": [-112.0, -111.5],
        "category": ["OIL", "OIL"],
        "label": ["CAISSON", "FIXED"],
        "sub_category": ["BOEM_GOM", "BOEM_GOM"],
        "first_timestamp": ["2010-01-01", "2015-06-15"],
        "last_timestamp": ["", ""],
        "source": ["BOEM_arcgis", "BOEM_arcgis"],
    })


@pytest.fixture
def mock_support_df():
    """DataFrame simulando buques de apoyo OSV."""
    return pd.DataFrame({
        "vessel_id": ["OSV001", "OSV002"],
        "mmsi": ["111111111", "222222222"],
        "imo": ["9000001", "9000002"],
        "shipname": ["OCEAN STAR", "GULF RUNNER"],
        "flag": ["MEX", "PAN"],
        "vessel_type": ["support", "support"],
        "gear_type": ["", ""],
        "lat": [26.5, 27.0],
        "lon": [-112.0, -111.5],
        "length_m": [60.0, 45.0],
        "tonnage_gt": [1500.0, 800.0],
        "source": ["GFW_support_vessels", "GFW_support_vessels"],
    })


@pytest.fixture
def mock_gaps_df():
    """DataFrame simulando AIS gap events."""
    return pd.DataFrame({
        "gap_id": ["G001", "G002"],
        "vessel_id": ["OSV001", "V999"],
        "mmsi": ["111111111", "333333333"],
        "shipname": ["OCEAN STAR", "UNKNOWN"],
        "flag": ["MEX", ""],
        "lat": [26.5, 28.0],
        "lon": [-112.0, -110.0],
        "start": ["2024-01-15T00:00:00.000Z", "2024-02-20T00:00:00.000Z"],
        "end": ["2024-01-15T12:00:00.000Z", "2024-02-21T06:00:00.000Z"],
        "gap_hours": [12.0, 30.0],
        "vessel_type": ["unknown", "unknown"],
        "source": ["GFW_gaps", "GFW_gaps"],
    })


@pytest.fixture
def mock_gfw_gdf(mock_gfw_df):
    """GeoDataFrame desde mock_gfw_df."""
    geometry = [Point(lon, lat) for lon, lat in zip(mock_gfw_df.lon, mock_gfw_df.lat)]
    return gpd.GeoDataFrame(mock_gfw_df, geometry=geometry, crs="EPSG:4326")


@pytest.fixture
def mock_obis_gdf(mock_obis_df):
    """GeoDataFrame desde mock_obis_df."""
    geometry = [
        Point(lon, lat)
        for lon, lat in zip(mock_obis_df.decimalLongitude, mock_obis_df.decimalLatitude)
    ]
    return gpd.GeoDataFrame(mock_obis_df, geometry=geometry, crs="EPSG:4326")


# ── Tests: Spatial Join ──────────────────────────────────────────────────────

class TestSpatialJoin:
    """Tests para src/pipeline/spatial_join.py."""

    def test_compute_risk_hotspots_creates_geojson(self, mock_gfw_gdf, mock_obis_gdf, tmp_path):
        from src.pipeline.spatial_join import compute_risk_hotspots
        output = str(tmp_path / "test_hotspots.geojson")
        result = compute_risk_hotspots(mock_gfw_gdf, mock_obis_gdf, output)
        assert os.path.exists(output)
        assert isinstance(result, gpd.GeoDataFrame)
        assert len(result) > 0

    def test_compute_risk_hotspots_has_required_columns(self, mock_gfw_gdf, mock_obis_gdf, tmp_path):
        from src.pipeline.spatial_join import compute_risk_hotspots
        output = str(tmp_path / "test_hotspots.geojson")
        result = compute_risk_hotspots(mock_gfw_gdf, mock_obis_gdf, output)
        for col in ["h3_index", "vessel_count", "megafauna_count", "risk_score"]:
            assert col in result.columns, f"Falta columna: {col}"

    def test_compute_risk_hotspots_risk_score_formula(self, mock_gfw_gdf, mock_obis_gdf, tmp_path):
        from src.pipeline.spatial_join import compute_risk_hotspots
        output = str(tmp_path / "test_hotspots.geojson")
        result = compute_risk_hotspots(mock_gfw_gdf, mock_obis_gdf, output)
        # Risk score = vessel_count * megafauna_count
        for _, row in result.iterrows():
            assert row.risk_score == row.vessel_count * row.megafauna_count

    def test_empty_dataframes(self, tmp_path):
        from src.pipeline.spatial_join import compute_risk_hotspots
        empty_gfw = gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:4326")
        empty_obis = gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:4326")
        output = str(tmp_path / "test_empty.geojson")
        result = compute_risk_hotspots(empty_gfw, empty_obis, output)
        assert os.path.exists(output)


# ── Tests: Knowledge Graph ───────────────────────────────────────────────────

class TestKnowledgeGraph:
    """Tests para src/pipeline/knowledge_graph.py."""

    def test_build_basic_graph(self, mock_gfw_df, mock_obis_df):
        from src.pipeline.knowledge_graph import build_knowledge_graph
        G = build_knowledge_graph(
            mock_gfw_df, mock_obis_df,
            enrich_vessels=False, enrich_iucn=False,
        )
        assert G.number_of_nodes() > 0
        assert G.number_of_edges() > 0
        # Debe tener nodos de tipo HexCell, VesselEvent, Species, MegafaunaOccurrence
        node_types = {d.get("type") for _, d in G.nodes(data=True)}
        assert "HexCell" in node_types
        assert "VesselEvent" in node_types
        assert "Species" in node_types
        assert "MegafaunaOccurrence" in node_types

    def test_build_graph_with_platforms(self, mock_gfw_df, mock_obis_df, mock_platforms_df):
        from src.pipeline.knowledge_graph import build_knowledge_graph
        G = build_knowledge_graph(
            mock_gfw_df, mock_obis_df,
            platforms_df=mock_platforms_df,
            enrich_vessels=False, enrich_iucn=False,
        )
        node_types = {d.get("type") for _, d in G.nodes(data=True)}
        assert "OilPlatform" in node_types
        # Debe haber aristas LOCATED_IN
        relations = {d.get("relation") for _, _, d in G.edges(data=True)}
        assert "LOCATED_IN" in relations

    def test_build_graph_with_support_vessels(
        self, mock_gfw_df, mock_obis_df, mock_platforms_df, mock_support_df
    ):
        from src.pipeline.knowledge_graph import build_knowledge_graph
        G = build_knowledge_graph(
            mock_gfw_df, mock_obis_df,
            platforms_df=mock_platforms_df,
            support_df=mock_support_df,
            enrich_vessels=False, enrich_iucn=False,
        )
        node_types = {d.get("type") for _, d in G.nodes(data=True)}
        assert "SupportVessel" in node_types
        relations = {d.get("relation") for _, _, d in G.edges(data=True)}
        assert "OPERATES_IN" in relations

    def test_build_graph_with_gaps(
        self, mock_gfw_df, mock_obis_df, mock_gaps_df
    ):
        from src.pipeline.knowledge_graph import build_knowledge_graph
        G = build_knowledge_graph(
            mock_gfw_df, mock_obis_df,
            gaps_df=mock_gaps_df,
            enrich_vessels=False, enrich_iucn=False,
        )
        node_types = {d.get("type") for _, d in G.nodes(data=True)}
        assert "AisGapEvent" in node_types
        relations = {d.get("relation") for _, _, d in G.edges(data=True)}
        assert "WENT_DARK_IN" in relations

    def test_build_full_graph_node_count(
        self, mock_gfw_df, mock_obis_df, mock_platforms_df, mock_support_df, mock_gaps_df
    ):
        from src.pipeline.knowledge_graph import build_knowledge_graph
        G = build_knowledge_graph(
            mock_gfw_df, mock_obis_df,
            platforms_df=mock_platforms_df,
            support_df=mock_support_df,
            gaps_df=mock_gaps_df,
            enrich_vessels=False, enrich_iucn=False,
        )
        # Verificar conteos mínimos esperados
        assert G.number_of_nodes() >= (4 + 5 + 2 + 2 + 2 + 4)  # vessels + obis + platforms + OSVs + gaps + species
        assert G.number_of_edges() >= 10

    def test_export_graph_json(self, mock_gfw_df, mock_obis_df, tmp_path):
        from src.pipeline.knowledge_graph import build_knowledge_graph, export_graph_json
        G = build_knowledge_graph(
            mock_gfw_df, mock_obis_df,
            enrich_vessels=False, enrich_iucn=False,
        )
        path = export_graph_json(G, str(tmp_path))
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert "nodes" in data
        assert "links" in data
        assert len(data["nodes"]) == G.number_of_nodes()

    def test_export_cypher(self, mock_gfw_df, mock_obis_df, tmp_path):
        from src.pipeline.knowledge_graph import build_knowledge_graph, export_cypher
        G = build_knowledge_graph(
            mock_gfw_df, mock_obis_df,
            enrich_vessels=False, enrich_iucn=False,
        )
        path = export_cypher(G, str(tmp_path))
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        assert "MERGE" in content
        assert "DETECTED_IN" in content


# ── Tests: API Routes ────────────────────────────────────────────────────────

class TestAPIRoutes:
    """Tests para src/api/routes.py (sin levantar servidor)."""

    def test_load_geojson_missing_file(self):
        from src.api.routes import _load_geojson
        result = _load_geojson("/tmp/nonexistent_file_ocean_proto_test.geojson")
        assert result == {"type": "FeatureCollection", "features": []}

    def test_load_geojson_valid_file(self, tmp_path):
        from src.api.routes import _load_geojson
        geojson = {"type": "FeatureCollection", "features": [{"type": "Feature"}]}
        path = str(tmp_path / "test.geojson")
        with open(path, "w") as f:
            json.dump(geojson, f)
        result = _load_geojson(path)
        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
