# White Paper — Ocean Proto: Maritime Intelligence Infrastructure
## Monitoring Mega-cruisers, Yachts, and Industrial Fishing in Baja California Sur
### Serverless Dashboard Layout Optimization & Knowledge Graph Visualizer under the Esoteria Design Doctrine

---

## 1. Executive Summary

**Ocean Proto** is a spatial and network analysis platform designed to evaluate the impact of human maritime activities on marine megafauna (primarily cetaceans) habitats in the Gulf of California and the coasts of Baja California Sur.

Recently, the project's focus pivoted from the *Oil & Gas* industry to monitoring:
1. **Mega-cruisers and Yachts**: Large-draft vessels (`passenger`) that introduce heavy acoustic noise and direct collision risks in transit channels and breeding areas.
2. **Industrial Fishing**: Active fleets (`fishing` / `support`) whose spatial footprint and effort alter trophic chains and critical habitats.
3. **Dark Events (AIS Gaps)**: Incidents where vessels disable their AIS transponders (`AisGapEvent`), suggesting potential illegal, unreported, or unregulated (IUU) fishing in protected marine sanctuaries.

This document outlines the dashboard layout optimization, the development of the interactive **Knowledge Graph** (KG) explorer, and the transition toward a **serverless cloud-native** architecture on Vercel and Supabase.

---

## 2. Dashboard Layout Optimization (Three-Column Design)

The original layout relied on floating overlay panels positioned directly over the Leaflet map. This obstructed geographical analysis and generated severe overlap issues on standard screen resolutions.

To address this, we implemented a structured **three-column layout** using CSS flexbox rules:

```
┌──────────────────────────────────────────────────────────────────┐
│                         HEADER (Esoteria)                        │
├──────────────┬────────────────────────────────────┬──────────────┤
│              │                                    │              │
│  [ MAPA ]    │                                    │   Intel      │
│  [ GRAFO ]   │            MAIN WORKSPACE          │   Panel      │
│              │            (Map or D3 Graph)       │              │
│  Layer       │                                    │  ──────────  │
│  Panel       │                                    │   KG         │
│              │                                    │   Panel      │
│ (Sidebar L)  │            [ StatsBar ]            │ (Sidebar R)  │
└──────────────┴────────────────────────────────────┴──────────────┘
```

### 2.1. Layout Features:
- **Left Sidebar (Control, 280px)**: Houses the main view toggle (**[ Map ] / [ Graph ]**) and the corresponding layer or filter options.
- **Right Sidebar (Analysis, 360px)**: Vertically stacks the marine traffic intelligence panel (`IntelPanel`) and the knowledge graph statistics panel (`KGPanel`) with custom scroll behavior.
- **Collapsible Sidebar Toggles**: Minimalist button handles (`◀`/`▶`) allow sidebars to collapse instantly to `width: 0`, expanding the main workspace to full-screen.
- **Leaflet ResizeObserver**: An observer attached to the map container automatically triggers `map.invalidateSize()` whenever sidebars expand or collapse, preventing Leaflet rendering glitches (grey zones).

---

## 3. Interactive D3.js Knowledge Graph Explorer

The Knowledge Graph models complex eco-anthropogenic relationships in the marine sanctuary. It contains **2,051 nodes** and **4,148 edges**, linking spatial cells (`HexCell`), megafauna occurrences (`MegafaunaOccurrence`), whale species (`WhaleSpecies`), permanent vessel identities (`VesselIdentity`), radio gaps (`AisGapEvent`), and high-collision risk zones (`RiskZone`).

### 3.1. Visual Digestibility & Performance Strategy:
Rendering a 2,000+ node graph directly in a browser results in an unreadable "hairball effect" and degrades client performance. We implemented a dual-scale filtering strategy:

1. **Macro-Graph View (No Focus)**: By default, the simulation displays only high-level conceptual nodes: whale species, risk zones, cruisers, industrial fishing vessels, and gaps. Individual hex cells and raw event points are hidden to keep the visualization clean and readable.
2. **Neighborhood Focus View (Focal Node)**: Double-clicking any node or choosing an entity from the search autocomplete centers the D3.js force simulation on that node and restricts the active graph to **only its 1-hop or 2-hop connections**. This isolates the context to 5-50 highly legible nodes.

### 3.2. Design Implementation (Esoteria Style Compliance):
Consistent with the institutional guidelines of the Esoteria Design System (v1.0), rounded corners, box shadows, and gradients are strictly prohibited. Nodes are drawn as sharp geometric SVG paths without anti-aliasing aesthetics:
- **WhaleSpecies / Species**: Cyan diamonds (`#44bbff`).
- **SupportVessel (Industrial Fishing)**: Green squares (`#22c55e`).
- **OilPlatform (Cruisers & Infrastructure)**: Violet squares (`#a855f7`).
- **AisGapEvent**: Yellow warning triangles (`#facc15`).
- **RiskZone**: Large red octagons/hexagons (`#ef4444`).
- **HexCell (Spatial Coordinate)**: Small slate-grey hexagons (`#475569`).

Edges are drawn as crisp, grey directional lines with arrowheads (`marker-end`). Hovering over a link highlights it and displays its semantic relationship type (e.g., `DARK_NEAR_WHALE`). A sidebar **Node Inspector** shows physical attributes (latitude/longitude, IUCN red list status, gap duration) and includes an interactive locator button to jump directly back to the map and fly the Leaflet camera to its coordinates.

---

## 4. Serverless Cloud-Native Architecture (Supabase + Vercel)

To deploy the Next.js frontend on Vercel without requiring a local running FastAPI process in production, we migrated all backend data storage and retrieval to **Supabase (PostgreSQL + PostgREST)**.

1. **`knowledge_graph` Table**: Created in Supabase to house the full graph structure in a JSONB format.
2. **RLS Security Policies**: Row Level Security (RLS) was enabled on the table, granting anonymous public read access (`SELECT`) while restricting write permissions (`INSERT`/`UPDATE`/`DELETE`) to administrative service keys.
3. **Data Pipeline Syncing**: The python backend continues to run the spatial join and graph extraction pipelines locally (`knowledge_graph.py`). Once the new `graph.json` is generated, a helper script pushes it directly to Supabase via a PostgREST `upsert` API call.
4. **Serverless Frontend Clients**:
   - `supabase.ts` now defines `db.knowledgeGraph()` and `db.kgStats()` to pull raw network structures directly from the Supabase client.
   - This eliminates the need for an active local API server, letting Vercel serve the interactive map and graph views completely serverless with global edge performance.

---

## 5. Conclusions and Future Directions

The re-designed **Ocean Proto** dashboard under the Esoteria design principles provides maritime researchers and conservation managers with a rigorous, high-performance web dashboard. By decoupling the interface and routing all geodatasets and relational graphs through Supabase, the platform is fully optimized for production on Vercel, paving the way for future integrations with real-time predictive machine learning models.
