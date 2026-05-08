-- Ocean Proto — Supabase Schema
-- Ejecutar en el SQL Editor de Supabase

-- Habilitar PostGIS
create extension if not exists postgis;

-- ============================================================
-- TABLE: risk_hotspots (H3 hexagons with IPA scoring)
-- ============================================================
create table if not exists risk_hotspots (
  id            bigserial primary key,
  h3_index      text not null unique,
  geom          geometry(Polygon, 4326),
  vessel_count            int default 0,
  score_traffic_density   float default 0,
  score_acoustic          float default 0,
  estimated_spl_db        float default 0,
  megafauna_count         int default 0,
  score_cooccurrence      float default 0,
  score_fishing_effort    float default 0,
  fishing_hours           float default 0,
  gap_count               int default 0,
  encounter_count         int default 0,
  loitering_count         int default 0,
  score_behavior_anomaly  float default 0,
  platform_count          int default 0,
  support_count           int default 0,
  score_og_pressure       float default 0,
  score_corridor_intensity float default 0,
  score_identity_risk     float default 0,
  ipa                     float default 0,
  temporal_modifier       float default 1,
  ipa_100                 float default 0,
  ipa_level               text default 'low',
  risk_score              float default 0,
  crs_100                 float default 0,
  crs_level               text default 'low',
  updated_at              timestamptz default now()
);

create index if not exists risk_hotspots_geom_idx on risk_hotspots using gist(geom);
create index if not exists risk_hotspots_ipa_idx on risk_hotspots(ipa_100 desc);

-- ============================================================
-- TABLE: vessels (SAR / AIS vessel detections)
-- ============================================================
create table if not exists vessels (
  id          bigserial primary key,
  mmsi        text,
  vessel_type text default 'other',
  detected_at timestamptz,
  geom        geometry(Point, 4326),
  updated_at  timestamptz default now()
);

create index if not exists vessels_geom_idx on vessels using gist(geom);
create index if not exists vessels_type_idx on vessels(vessel_type);

-- ============================================================
-- TABLE: megafauna (OBIS cetacean occurrences)
-- ============================================================
create table if not exists megafauna (
  id           bigserial primary key,
  species      text not null,
  taxa_group   text,
  oil_relevance text,
  observed_at  timestamptz,
  geom         geometry(Point, 4326),
  updated_at   timestamptz default now()
);

create index if not exists megafauna_geom_idx on megafauna using gist(geom);
create index if not exists megafauna_species_idx on megafauna(species);

-- ============================================================
-- TABLE: oil_platforms (BOEM + GFW fixed infrastructure)
-- ============================================================
create table if not exists oil_platforms (
  id          bigserial primary key,
  platform_id text,
  category    text default 'OIL',
  label       text,
  source      text,
  geom        geometry(Point, 4326),
  updated_at  timestamptz default now()
);

create index if not exists oil_platforms_geom_idx on oil_platforms using gist(geom);

-- ============================================================
-- TABLE: gap_events (AIS disablement events)
-- ============================================================
create table if not exists gap_events (
  id          bigserial primary key,
  gap_id      text,
  vessel_id   text,
  mmsi        text,
  shipname    text,
  flag        text,
  gap_hours   float,
  gap_start   timestamptz,
  gap_end     timestamptz,
  geom        geometry(Point, 4326),
  updated_at  timestamptz default now()
);

create index if not exists gap_events_geom_idx on gap_events using gist(geom);

-- ============================================================
-- TABLE: support_vessels (OSVs - Offshore Supply Vessels)
-- ============================================================
create table if not exists support_vessels (
  id          bigserial primary key,
  vessel_id   text,
  mmsi        text,
  shipname    text,
  flag        text,
  vessel_type text default 'support',
  geom        geometry(Point, 4326),
  updated_at  timestamptz default now()
);

create index if not exists support_vessels_geom_idx on support_vessels using gist(geom);

-- ============================================================
-- RLS: Habilitar acceso de lectura público (anon key)
-- ============================================================
alter table risk_hotspots  enable row level security;
alter table vessels         enable row level security;
alter table megafauna       enable row level security;
alter table oil_platforms   enable row level security;
alter table gap_events      enable row level security;
alter table support_vessels enable row level security;

-- Políticas de lectura pública (anon)
create policy "public read risk_hotspots"  on risk_hotspots  for select using (true);
create policy "public read vessels"         on vessels         for select using (true);
create policy "public read megafauna"       on megafauna       for select using (true);
create policy "public read oil_platforms"   on oil_platforms   for select using (true);
create policy "public read gap_events"      on gap_events      for select using (true);
create policy "public read support_vessels" on support_vessels for select using (true);

-- ============================================================
-- HELPER: GeoJSON FeatureCollection desde tabla
-- ============================================================
create or replace function get_risk_hotspots_geojson()
returns json language sql stable as $$
  select json_build_object(
    'type', 'FeatureCollection',
    'features', coalesce(json_agg(
      json_build_object(
        'type', 'Feature',
        'geometry', st_asgeojson(geom)::json,
        'properties', json_build_object(
          'h3_index', h3_index,
          'ipa', ipa,
          'ipa_100', ipa_100,
          'ipa_level', ipa_level,
          'risk_score', risk_score,
          'crs_100', crs_100,
          'crs_level', crs_level,
          'vessel_count', vessel_count,
          'megafauna_count', megafauna_count,
          'estimated_spl_db', estimated_spl_db,
          'gap_count', gap_count,
          'score_acoustic', score_acoustic,
          'score_og_pressure', score_og_pressure
        )
      )
    ), '[]'::json)
  )
  from risk_hotspots;
$$;
