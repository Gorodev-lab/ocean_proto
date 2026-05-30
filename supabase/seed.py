"""
supabase/seed.py — Carga los datos procesados del pipeline en Supabase.

Uso:
  SUPABASE_URL=https://xxx.supabase.co \
  SUPABASE_SERVICE_KEY=eyJ... \
  python supabase/seed.py
"""

import os, json, requests, sys
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")   # service_role key (para escritura)

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY env vars")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",  # upsert
}

BASE_API = "http://localhost:8080"   # FastAPI local

def fetch_geojson(endpoint: str) -> list[dict]:
    """Fetch GeoJSON from local FastAPI and convert to flat row dicts."""
    r = requests.get(f"{BASE_API}{endpoint}", timeout=30)
    r.raise_for_status()
    return r.json().get("features", [])


def upsert(table: str, rows: list[dict]) -> None:
    """Upsert rows into a Supabase table in batches of 500."""
    BATCH = 500
    total = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i+BATCH]
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=HEADERS,
            json=batch,
        )
        if r.status_code not in (200, 201):
            print(f"  ✗ {table} batch {i//BATCH}: {r.status_code} — {r.text[:200]}")
        else:
            total += len(batch)
    print(f"  ✓ {table}: {total} rows upserted")


def point_geom(lon: float, lat: float) -> str:
    return f"SRID=4326;POINT({lon} {lat})"


# ── 1. risk_hotspots ─────────────────────────────────────────
print("Loading risk_hotspots...")
features = fetch_geojson("/api/risk-hotspots")
rows = []
for f in features:
    props = f.get("properties", {})
    geom  = f.get("geometry", {})
    # Convert GeoJSON geometry to WKT for PostgREST
    coords = geom.get("coordinates", [[]])[0]
    wkt_coords = ", ".join(f"{c[0]} {c[1]}" for c in coords)
    rows.append({
        "h3_index": props.get("h3_index"),
        "geom": f"SRID=4326;POLYGON(({wkt_coords}))",
        "vessel_count":             int(props.get("vessel_count", 0)),
        "score_traffic_density":    props.get("score_traffic_density", 0),
        "score_acoustic":           props.get("score_acoustic", 0),
        "estimated_spl_db":         props.get("estimated_spl_db", 0),
        "megafauna_count":          int(props.get("megafauna_count", 0)),
        "score_cooccurrence":       props.get("score_cooccurrence", 0),
        "score_fishing_effort":     props.get("score_fishing_effort", 0),
        "fishing_hours":            props.get("fishing_hours", 0),
        "gap_count":                int(props.get("gap_count", 0)),
        "encounter_count":          int(props.get("encounter_count", 0)),
        "loitering_count":          int(props.get("loitering_count", 0)),
        "score_behavior_anomaly":   props.get("score_behavior_anomaly", 0),
        "platform_count":           int(props.get("platform_count", 0)),
        "support_count":            int(props.get("support_count", 0)),
        "score_og_pressure":        props.get("score_og_pressure", 0),
        "score_corridor_intensity": props.get("score_corridor_intensity", 0),
        "score_identity_risk":      props.get("score_identity_risk", 0),
        "ipa":                      props.get("ipa", 0),
        "temporal_modifier":        props.get("temporal_modifier", 1),
        "ipa_100":                  props.get("ipa_100", 0),
        "ipa_level":                props.get("ipa_level", "low"),
        "risk_score":               props.get("risk_score", 0),
        "crs_100":                  props.get("crs_100", 0),
        "crs_level":                props.get("crs_level", "low"),
    })
upsert("risk_hotspots", rows)


# ── 2. vessels ───────────────────────────────────────────────
print("Loading vessels...")
features = fetch_geojson("/api/vessels")
rows = []
for f in features:
    props = f.get("properties", {})
    coords = f.get("geometry", {}).get("coordinates", [0, 0])
    ts = props.get("timestamp")
    rows.append({
        "mmsi":        str(props.get("mmsi", "")),
        "vessel_type": props.get("vessel_type", "other"),
        "detected_at": ts if ts else None,
        "geom":        point_geom(coords[0], coords[1]),
    })
upsert("vessels", rows)


# ── 3. megafauna ─────────────────────────────────────────────
print("Loading megafauna...")
features = fetch_geojson("/api/megafauna/")
rows = []
for f in features:
    props = f.get("properties", {})
    coords = f.get("geometry", {}).get("coordinates", [0, 0])
    ts = props.get("timestamp")
    rows.append({
        "species":      props.get("species", ""),
        "taxa_group":   props.get("taxa_group"),
        "oil_relevance":props.get("oil_relevance"),
        "observed_at":  ts if ts else None,
        "geom":         point_geom(coords[0], coords[1]),
    })
upsert("megafauna", rows)


# ── 4. oil_platforms ─────────────────────────────────────────
print("Loading oil_platforms...")
features = fetch_geojson("/api/oil-platforms")
rows = []
for f in features:
    props = f.get("properties", {})
    coords = f.get("geometry", {}).get("coordinates", [0, 0])
    rows.append({
        "platform_id": props.get("platform_id", ""),
        "category":    props.get("category", "OIL"),
        "label":       props.get("label", ""),
        "source":      props.get("source", ""),
        "geom":        point_geom(coords[0], coords[1]),
    })
if rows:
    upsert("oil_platforms", rows)
else:
    print("  ↷ oil_platforms: no data to load")


# ── 5. gap_events ────────────────────────────────────────────
print("Loading gap_events...")
features = fetch_geojson("/api/gap-events")
rows = []
for f in features:
    props = f.get("properties", {})
    coords = f.get("geometry", {}).get("coordinates", [0, 0])
    rows.append({
        "gap_id":    props.get("gap_id", ""),
        "vessel_id": props.get("vessel_id", ""),
        "mmsi":      str(props.get("mmsi", "")),
        "shipname":  props.get("shipname", ""),
        "flag":      props.get("flag", ""),
        "gap_hours": props.get("gap_hours", 0),
        "gap_start": props.get("start"),
        "gap_end":   props.get("end"),
        "geom":      point_geom(coords[0], coords[1]) if coords[0] else None,
    })
if rows:
    upsert("gap_events", rows)
else:
    print("  ↷ gap_events: no data to load")


print("\n✅ Seed completado.")
