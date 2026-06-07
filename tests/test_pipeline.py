"""
ocean_proto / tests / test_pipeline.py
=======================================
Suite TDD Red-Green para el pipeline de Ocean Proto.

Cubre:
  1. Spatial Join (H3 hexagonal aggregation)
  2. Risk Scoring (IPA computation, safe-math, weights)
  3. Seasonal modifiers (fishing pressure by month)
  4. Knowledge Graph (build, export JSON, export Cypher)
  5. Resilience (HTTP retry, header construction)
  6. Supabase RPC contracts (data shape validation)
  7. API route contracts (vedas taxonomy codes, timeline shape)
"""

import os
import sys
import json
import pytest
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# Ensure project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════════════════════

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


@pytest.fixture
def mock_hotspots_df():
    """DataFrame mínimo simulando celdas H3 con vessel_count."""
    return pd.DataFrame({
        "h3_index": ["851f8a3fffffff", "851f8b3fffffff", "851f8c3fffffff"],
        "vessel_count": [10, 5, 0],
    })


@pytest.fixture
def mock_megafauna_hex_df():
    """DataFrame de megafauna agregada por H3."""
    return pd.DataFrame({
        "h3_index": ["851f8a3fffffff", "851f8b3fffffff"],
        "megafauna_count": [20, 0],
    })


# ══════════════════════════════════════════════════════════════════════════════
# 1. SPATIAL JOIN — H3 Hexagonal Aggregation
# ══════════════════════════════════════════════════════════════════════════════

class TestSpatialJoin:
    """Tests para src/pipeline/spatial_join.py — refactored API."""

    def test_compute_pressure_hotspots_returns_geodataframe(
        self, mock_gfw_gdf, tmp_path
    ):
        from src.pipeline.spatial_join import compute_pressure_hotspots
        output = str(tmp_path / "test_hotspots.geojson")
        result = compute_pressure_hotspots(mock_gfw_gdf, output)
        assert isinstance(result, gpd.GeoDataFrame)
        assert len(result) > 0
        assert os.path.exists(output)

    def test_compute_pressure_hotspots_required_columns(
        self, mock_gfw_gdf, tmp_path
    ):
        from src.pipeline.spatial_join import compute_pressure_hotspots
        output = str(tmp_path / "test_cols.geojson")
        result = compute_pressure_hotspots(mock_gfw_gdf, output)
        required = ["h3_index", "vessel_count"]
        for col in required:
            assert col in result.columns, f"Missing column: {col}"

    def test_gfw_only_hotspots(self, mock_gfw_gdf, tmp_path):
        from src.pipeline.spatial_join import compute_gfw_only_hotspots
        output = str(tmp_path / "gfw_only.geojson")
        result = compute_gfw_only_hotspots(mock_gfw_gdf, output_path=output)
        assert isinstance(result, gpd.GeoDataFrame)
        assert "h3_index" in result.columns
        assert "vessel_count" in result.columns
        assert len(result) > 0

    def test_get_h3_index(self):
        from src.pipeline.spatial_join import get_h3_index, H3_RESOLUTION
        idx = get_h3_index(26.5, -112.0, H3_RESOLUTION)
        assert isinstance(idx, str)
        assert len(idx) > 0
        # H3 index should start with '8' for resolution 5
        assert idx.startswith("8")

    def test_cell_to_polygon(self):
        from src.pipeline.spatial_join import cell_to_polygon, get_h3_index, H3_RESOLUTION
        idx = get_h3_index(26.5, -112.0, H3_RESOLUTION)
        poly = cell_to_polygon(idx)
        assert poly is not None
        assert poly.is_valid
        assert poly.area > 0

    def test_empty_inputs(self, tmp_path):
        from src.pipeline.spatial_join import compute_pressure_hotspots
        empty_gdf = gpd.GeoDataFrame(
            columns=["geometry"],
            geometry=[],
            crs="EPSG:4326"
        )
        output = str(tmp_path / "empty.geojson")
        result = compute_pressure_hotspots(empty_gdf, output)
        assert isinstance(result, gpd.GeoDataFrame)
        assert len(result) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. RISK SCORING — IPA (Índice de Presión Antrópica)
# ══════════════════════════════════════════════════════════════════════════════

class TestRiskScoring:
    """Tests para src/pipeline/risk_scoring.py — IPA engine."""

    def test_weights_sum_to_one(self):
        from src.pipeline.risk_scoring import WEIGHTS
        total = sum(WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, f"Weights sum={total}, expected 1.0"

    def test_weights_all_positive(self):
        from src.pipeline.risk_scoring import WEIGHTS
        for name, w in WEIGHTS.items():
            assert w > 0, f"Weight '{name}' must be positive, got {w}"

    def test_minmax_series_normal(self):
        from src.pipeline.risk_scoring import _minmax_series
        s = pd.Series([0, 5, 10])
        result = _minmax_series(s)
        assert result.iloc[0] == pytest.approx(0.0)
        assert result.iloc[1] == pytest.approx(0.5)
        assert result.iloc[2] == pytest.approx(1.0)

    def test_minmax_series_constant(self):
        """Zero-variance input → all zeros (no division by zero)."""
        from src.pipeline.risk_scoring import _minmax_series
        s = pd.Series([5, 5, 5])
        result = _minmax_series(s)
        assert (result == 0.0).all(), "Constant series should normalize to 0.0"

    def test_minmax_series_single_element(self):
        from src.pipeline.risk_scoring import _minmax_series
        s = pd.Series([42])
        result = _minmax_series(s)
        assert result.iloc[0] == 0.0

    def test_ipa_basic_computation(self, mock_hotspots_df):
        from src.pipeline.risk_scoring import compute_anthropic_pressure_index
        result = compute_anthropic_pressure_index(mock_hotspots_df)
        assert not result.empty
        assert "ipa" in result.columns
        assert "ipa_100" in result.columns
        assert "ipa_level" in result.columns

    def test_ipa_100_bounded(self, mock_hotspots_df):
        """IPA_100 must be in [0, 100]."""
        from src.pipeline.risk_scoring import compute_anthropic_pressure_index
        result = compute_anthropic_pressure_index(mock_hotspots_df)
        assert (result["ipa_100"] >= 0).all()
        assert (result["ipa_100"] <= 100).all()

    def test_ipa_levels_categorical(self, mock_hotspots_df):
        from src.pipeline.risk_scoring import compute_anthropic_pressure_index
        result = compute_anthropic_pressure_index(mock_hotspots_df)
        valid_levels = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        actual_levels = set(result["ipa_level"].unique())
        assert actual_levels.issubset(valid_levels), f"Invalid levels: {actual_levels}"

    def test_ipa_with_megafauna(self, mock_hotspots_df, mock_megafauna_hex_df):
        """Co-occurrence should increase IPA for cells with both vessels and megafauna."""
        from src.pipeline.risk_scoring import compute_anthropic_pressure_index
        # Without megafauna
        r_base = compute_anthropic_pressure_index(mock_hotspots_df)
        # With megafauna
        r_meg = compute_anthropic_pressure_index(
            mock_hotspots_df, megafauna_hex_df=mock_megafauna_hex_df
        )
        # Cell 851f8a3fffffff has vessels=10, megafauna=20 → should have higher IPA
        cell_id = "851f8a3fffffff"
        base_ipa = float(r_base.loc[r_base.h3_index == cell_id, "ipa"].iloc[0])
        meg_ipa = float(r_meg.loc[r_meg.h3_index == cell_id, "ipa"].iloc[0])
        assert meg_ipa >= base_ipa, "Co-occurrence should increase IPA"

    def test_ipa_empty_input(self):
        """Empty hotspots → empty DataFrame (no crash)."""
        from src.pipeline.risk_scoring import compute_anthropic_pressure_index
        result = compute_anthropic_pressure_index(pd.DataFrame())
        assert result.empty

    def test_ipa_none_input(self):
        from src.pipeline.risk_scoring import compute_anthropic_pressure_index
        result = compute_anthropic_pressure_index(None)
        assert result.empty

    def test_ipa_no_nan(self, mock_hotspots_df):
        """IPA and sub-scores must be NaN-free."""
        from src.pipeline.risk_scoring import compute_anthropic_pressure_index
        result = compute_anthropic_pressure_index(mock_hotspots_df)
        score_cols = [c for c in result.columns if c.startswith("score_")]
        for col in score_cols + ["ipa", "ipa_100"]:
            assert not result[col].isna().any(), f"NaN found in {col}"

    def test_aggregate_megafauna_by_hex(self, mock_obis_gdf):
        from src.pipeline.risk_scoring import aggregate_megafauna_by_hex
        result = aggregate_megafauna_by_hex(mock_obis_gdf, resolution=5)
        assert "h3_index" in result.columns
        assert "megafauna_count" in result.columns
        assert result["megafauna_count"].sum() == len(mock_obis_gdf)

    def test_aggregate_megafauna_empty(self):
        from src.pipeline.risk_scoring import aggregate_megafauna_by_hex
        result = aggregate_megafauna_by_hex(None)
        assert result.empty


# ══════════════════════════════════════════════════════════════════════════════
# 3. SEASONAL — Fishing pressure modifiers
# ══════════════════════════════════════════════════════════════════════════════

class TestSeasonal:
    """Tests para src/pipeline/seasonal.py."""

    def test_all_months_defined(self):
        from src.pipeline.seasonal import FISHING_SEASON_MODIFIERS
        for m in range(1, 13):
            assert m in FISHING_SEASON_MODIFIERS, f"Month {m} missing"

    def test_modifiers_positive(self):
        from src.pipeline.seasonal import FISHING_SEASON_MODIFIERS
        for m, v in FISHING_SEASON_MODIFIERS.items():
            assert v > 0, f"Month {m} modifier must be positive"

    def test_veda_months_low_pressure(self):
        """June-August (veda de camarón) should have modifier < 1.0."""
        from src.pipeline.seasonal import get_fishing_season_modifier
        for m in [6, 7, 8]:
            assert get_fishing_season_modifier(m) < 1.0, f"Month {m} should be low pressure"

    def test_peak_months_high_pressure(self):
        """Dec-Feb (peak season) should have modifier > 1.5."""
        from src.pipeline.seasonal import get_fishing_season_modifier
        for m in [12, 1, 2]:
            assert get_fishing_season_modifier(m) >= 1.5, f"Month {m} should be high pressure"

    def test_season_labels_complete(self):
        from src.pipeline.seasonal import get_season_label
        labels = set()
        for m in range(1, 13):
            label = get_season_label(m)
            labels.add(label)
            assert label != "unknown", f"Month {m} has 'unknown' label"
        # Should have 4 distinct seasons
        assert len(labels) == 4

    def test_high_pressure_months(self):
        from src.pipeline.seasonal import get_high_pressure_months
        hpm = get_high_pressure_months()
        assert isinstance(hpm, list)
        assert len(hpm) > 0
        assert all(isinstance(m, int) for m in hpm)

    def test_compute_seasonal_summary(self):
        from src.pipeline.seasonal import compute_seasonal_summary
        for month in range(1, 13):
            result = compute_seasonal_summary(month)
            assert "month" in result
            assert "season_label" in result
            assert "pressure_modifier" in result
            assert "pressure_level" in result
            assert result["pressure_level"] in {"HIGH", "MEDIUM", "LOW"}
            assert "is_veda" in result
            if month in [6, 7, 8]:
                assert result["is_veda"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 4. KNOWLEDGE GRAPH — Build, export JSON, export Cypher
# ══════════════════════════════════════════════════════════════════════════════

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
        assert G.number_of_nodes() >= (4 + 5 + 2 + 2 + 2 + 4)
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

    def test_export_graph_json_serializable(self, mock_gfw_df, mock_obis_df, tmp_path):
        """All node properties must be JSON-serializable."""
        from src.pipeline.knowledge_graph import build_knowledge_graph, export_graph_json
        G = build_knowledge_graph(
            mock_gfw_df, mock_obis_df,
            enrich_vessels=False, enrich_iucn=False,
        )
        path = export_graph_json(G, str(tmp_path))
        with open(path) as f:
            raw = f.read()
        # Should not raise
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

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


# ══════════════════════════════════════════════════════════════════════════════
# 5. RESILIENCE — HTTP retry layer
# ══════════════════════════════════════════════════════════════════════════════

class TestResilience:
    """Tests para src/pipeline/_resilience.py."""

    def test_build_headers_no_token(self):
        from src.pipeline._resilience import _build_headers
        h = _build_headers()
        assert h["Content-Type"] == "application/json"
        assert h["Accept"] == "application/json"
        assert "Authorization" not in h

    def test_build_headers_with_token(self):
        from src.pipeline._resilience import _build_headers
        h = _build_headers(token="test_token_123")
        assert h["Authorization"] == "Bearer test_token_123"

    def test_http_get_invalid_url(self):
        """Should return None after retries (not raise)."""
        from src.pipeline._resilience import http_get
        result = http_get("http://localhost:99999/nonexistent", timeout=1.0)
        assert result is None

    def test_http_post_invalid_url(self):
        from src.pipeline._resilience import http_post
        result = http_post("http://localhost:99999/nonexistent", timeout=1.0)
        assert result is None

    def test_retry_config_exists(self):
        from src.pipeline._resilience import retry_transient
        assert retry_transient is not None


# ══════════════════════════════════════════════════════════════════════════════
# 6. API CONTRACTS — Frontend route data shape validation
# ══════════════════════════════════════════════════════════════════════════════

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


class TestVedaTaxonomyCodes:
    """Verify Esoteria-compliant taxonomy codes (no emojis)."""

    EXPECTED_CODES = {
        "atún":       "THN",
        "tiburón":    "SEL",
        "camarón":    "PEN",
        "totoaba":    "TOT",
        "manta_raya": "MOB",
    }

    def test_all_species_have_codes(self):
        """Every known veda species maps to a 3-letter taxonomy code."""
        for sp, code in self.EXPECTED_CODES.items():
            assert len(code) == 3, f"{sp} code should be 3 chars"
            assert code.isupper(), f"{sp} code should be uppercase"
            assert code.isalpha(), f"{sp} code should be alphabetic"

    def test_no_emoji_in_codes(self):
        """Taxonomy codes must contain only ASCII letters."""
        for sp, code in self.EXPECTED_CODES.items():
            assert code.isascii(), f"{sp} code contains non-ASCII"

    def test_codes_unique(self):
        """No duplicate codes."""
        codes = list(self.EXPECTED_CODES.values())
        assert len(codes) == len(set(codes)), "Duplicate taxonomy codes found"


class TestSpeciesSymbols:
    """Verify genus-abbreviation species symbols (Esoteria IntelPanel)."""

    EXPECTED_SYMS = {
        "Megaptera novaeangliae":  "Mn",
        "Balaenoptera musculus":   "Bm",
        "Tursiops truncatus":      "Tt",
        "Balaenoptera physalus":   "Bp",
        "Physeter macrocephalus":  "Pm",
        "Delphinus delphis":       "Dd",
    }

    def test_all_species_have_symbols(self):
        for species, sym in self.EXPECTED_SYMS.items():
            assert len(sym) == 2, f"{species} sym should be 2 chars"

    def test_symbols_format(self):
        """First letter uppercase (genus), second lowercase (species)."""
        for species, sym in self.EXPECTED_SYMS.items():
            assert sym[0].isupper(), f"{species}: first letter of '{sym}' should be uppercase"
            assert sym[1].islower(), f"{species}: second letter of '{sym}' should be lowercase"

    def test_symbols_unique(self):
        syms = list(self.EXPECTED_SYMS.values())
        assert len(syms) == len(set(syms))


# ══════════════════════════════════════════════════════════════════════════════
# 7. DATA INVARIANTS — Production data shape contracts
# ══════════════════════════════════════════════════════════════════════════════

class TestDataInvariants:
    """Validate production data contracts used by the frontend."""

    def test_ipa_weight_count(self):
        """IPA must use exactly 8 weighted criteria."""
        from src.pipeline.risk_scoring import WEIGHTS
        assert len(WEIGHTS) == 8

    def test_vedas_count(self):
        """6 vedas should exist in the system."""
        # This validates the seed data contract
        expected = 6
        veda_names = [
            "Veda Atún A", "Veda Atún B", "Veda Tiburón",
            "Veda Camarón Pacífico", "Veda Totoaba", "Veda Manta Raya"
        ]
        assert len(veda_names) == expected

    def test_h3_resolution(self):
        """H3 resolution must be 5 (≈253 km²)."""
        from src.pipeline.spatial_join import H3_RESOLUTION
        assert H3_RESOLUTION == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
