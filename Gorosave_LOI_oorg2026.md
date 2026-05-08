# Guardians of the Gulf: AI-Augmented Composite Risk Intelligence for Marine Megafauna Conservation in the Gulf of California

## 1. Project Title and Applicant Information

**Project Title:** Guardians of the Gulf: AI-Augmented Composite Risk Intelligence for Marine Megafauna Conservation in the Gulf of California

**Applicant:** Enrique Gorosave Meza (Individual)
**Affiliation:** Esoteria — Intelligence Infrastructure (Independent Research Center)
**Contact:**
- Email: gorosave@esoteriaai.com
- Address: La Paz, Baja California Sur, México
- Phone: +52 615 161 5001

**Relevant Qualifications:** The applicant holds expertise in bioengineering and applied AI systems for environmental governance. As founder of Esoteria, he has designed and deployed multiple intelligence infrastructure platforms for civic and environmental applications, including: (1) **Zohar Agent** — an agentic AI pipeline for automated extraction and structuring of Mexico's SEMARNAT environmental impact assessment records (Gaceta Ecológica), transforming unstructured government PDFs into auditable geospatial intelligence using sovereign edge-computing and VLM architectures; (2) **Denuncia Popular** — a citizen science platform for geolocated environmental crime reporting, integrating Google Gemini AI with enterprise geolocation to generate legally-certified environmental complaints; and (3) **Ocean Proto** — the working prototype for this proposal, a geospatial risk analytics platform already ingesting GFW API v3 data (fishing effort, encounters, loitering, SAR detections), OBIS marine megafauna occurrence records (42 cetacean species), and NOAA oceanographic variables into an H3 hexagonal grid scoring engine. This combination of bioengineering, AI systems engineering, environmental data pipeline development, and direct operational presence in Baja California Sur positions the applicant to execute the proposed work with minimal ramp-up.

## 2. Project Summary

### Research Goal
To develop and validate a **Composite Risk Score (CRS)** framework that quantifies multidimensional anthropogenic threats to marine megafauna in the Gulf of California by fusing multiple Global Fishing Watch datasets with biological and oceanographic variables through an AI-augmented analytical pipeline.

### Objectives
1. **Quantify spatiotemporal risk** by integrating GFW fishing effort (AIS + VMS), vessel presence, encounter events, loitering events, and SAR vessel detections into an 8-criterion Anthropogenic Pressure Index scored on H3 hexagonal cells (resolution 5 and 7).
2. **Model species-fleet interaction hotspots** by correlating GFW activity layers with OBIS cetacean occurrence data (blue whale, humpback whale, whale shark) and GFW-native environmental variables (SST, chlorophyll-a) to identify convergence zones where high biological value overlaps with intense human pressure.
3. **Deploy an AI agent** (Gemini-based) that enables natural-language querying of the risk graph network, generating automated hotspot narratives, temporal trend analysis, and regional synthesis reports — piloting the value of GFW data in agentic AI applications (Topic 6).
4. **Produce open-source deliverables:** a publicly accessible risk dashboard, the CRS methodology as a reproducible Python package, and a peer-reviewed manuscript.

### Global Fishing Watch Datasets and Platforms
Data availability has been **validated directly on the GFW Map platform** (May 8, 2026) for the study region. The following datasets will be used:

| GFW Dataset | Usage in CRS | Availability Confirmed |
|:------------|:-------------|:----------------------:|
| Apparent Fishing Effort (AIS) | Primary pressure indicator | ✓ |
| Apparent Fishing Effort (VMS) | Complementary effort validation (Mexico included) | ✓ |
| Vessel Presence | Shipping traffic density and acoustic modeling | ✓ |
| Encounter Events (AIS) | Transshipment risk indicator (Carrier↔Fishing) | ✓ (>3,000 events in region) |
| Loitering Events (AIS) | At-sea transfer suspicion scoring | ✓ |
| Radar Vessel Detections (SAR) | Dark fleet detection (AIS-unmatched vessels) | ✓ |
| Port Visit Events (AIS) | Fleet behavioral pattern analysis | ✓ |
| SST & Chlorophyll-a (Environment) | Biological habitat suitability modeling | ✓ (1/20° resolution) |

API access via `gfw-api-python-client` (v3) and BigQuery (`global-fishing-watch.fishing_effort_v3`) are already integrated in the existing prototype.

### Geographic Focus
**Gulf of California and Pacific coast of Baja California Sur** (22°–32°N, 118°–105°W). This region hosts critical feeding and breeding habitat for IUCN-listed cetaceans alongside one of Mexico's most intensive industrial fishing zones — a convergence validated through our GFW Map stress test showing dense overlap between high chlorophyll-a productivity areas and concentrated fishing effort.

### Methodology
The analytical pipeline follows four stages:
1. **Data Ingestion:** Automated extraction from GFW APIs (v3), OBIS v3, and NOAA ERDDAP into a unified schema with H3 spatial indexing.
2. **Risk Scoring:** Each H3 cell receives a normalized Composite Risk Score aggregating: fishing effort density, vessel transit intensity, encounter frequency, loitering density, SAR-AIS discrepancy (dark fleet proxy), SST suitability, chlorophyll-a concentration, and megafauna occurrence density.
3. **AI Analysis:** A Gemini-based agentic system traverses the scored knowledge graph to generate natural-language risk assessments, identify emerging hotspots, and produce structured reports.
4. **Validation & Output:** Cross-validation against known Marine Protected Areas (Cabo Pulmo, Loreto Bay) and published cetacean telemetry data. Outputs include an open-source dashboard, reproducible CRS package, and a peer-reviewed publication.

### Timeline
- **Months 1–4:** Full data pipeline deployment, CRS calibration, and Bayesian weight estimation.
- **Months 5–9:** AI agent development, dashboard deployment, and stakeholder consultation with local conservation organizations in La Paz, BCS.
- **Months 10–12:** Manuscript preparation, open-source release, and results dissemination.

## 3. Project Budget

| Category | Amount (USD) |
|:---------|-------------:|
| Cloud computing (GCP/BigQuery, Supabase hosting) | $3,000 |
| Data processing & API costs (GFW, OBIS, NOAA) | $1,500 |
| AI inference costs (Gemini API for agentic pipeline) | $1,500 |
| Equipment & field validation (local stakeholder engagement, BCS) | $2,000 |
| Publication fees (open-access journal) | $1,500 |
| Contingency | $500 |
| **Total** | **$10,000** |
