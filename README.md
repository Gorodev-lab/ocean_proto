# Ocean Proto

**Spatiotemporal collision and acoustic risk mapping for cetaceans in the Gulf of California** — fusing Global Fishing Watch vessel activity with OBIS megafauna occurrence data.

Ocean Proto evaluates where human maritime activity overlaps with critical cetacean habitat: industrial fishing effort, mega-cruisers and yachts transiting breeding areas, and **dark vessels** (AIS-gap events suggesting IUU fishing inside protected waters). The output is a Composite Risk Score on an Uber H3 grid, exposed through an API, a knowledge graph, and a dashboard.

## Data sources

- **Global Fishing Watch API v3** — fishing effort, encounters, loitering, AIS-gap events, and satellite SAR detections
- **OBIS** — marine megafauna occurrence records (42 cetacean species)
- **NOAA** — oceanographic variables (sea surface temperature, currents, bathymetry-derived features)

## How it works

```
ingest (gfw_client, obis_client, oceanographic)
    -> clean / normalize (pandas, geopandas)
    -> spatial_join on Uber H3
    -> acoustic_model (noise exposure)
    -> risk_scoring -> Composite Risk Score per hexagon
    -> graph_emitter -> Neo4j knowledge graph (Cypher)
    -> FastAPI service (uvicorn :8080) + Next.js frontend
```

- **Pipeline** (`src/pipeline/`): resilient ingestion with retry/backoff (`tenacity`), spatial joins, acoustic modeling, H3 risk scoring, and a Cypher graph emitter.
- **API** (`src/api/`): FastAPI application serving risk, megafauna and route endpoints, plus static dashboard.
- **Frontend** (`frontend/`): Next.js app with serverless API routes: `bay-health`, `conditions`, `conflict-zones`, `fishing-effort`, `intelligence`, `tides`, `timeline`.
- **Graph** (`data/knowledge_graph.cypher`, `src/scripts/build_knowledge_graph.py`): vessel/fauna interaction graph for network analysis.
- **Storage** (`supabase/`): PostgreSQL schema and seed script for the serverless deployment.

## Quickstart

```bash
# Backend
printf 'GFW_TOKEN=your_token\n' > .env   # see src/pipeline/gfw_client.py
pip install -r requirements.txt
python src/scripts/generate_mock_data.py          # or place real GFW exports under ./data
python src/scripts/build_knowledge_graph.py
uvicorn src.api.main:app --port 8080              # or: docker compose up (ocean_api on :8080)

# Frontend
cd frontend && npm install && npm run dev
```

Tests: `pytest tests/`

## Documentation

- `WHITE_PAPER_EN.md` / `WHITE_PAPER_ES.md` — platform design and dashboard architecture

## Author

**Enrique Gorosave Meza** — Esoteria · [github.com/Gorodev-lab](https://github.com/Gorodev-lab)
