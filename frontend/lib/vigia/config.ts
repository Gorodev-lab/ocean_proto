/**
 * lib/vigia/config.ts — Configuración central del pipeline de monitoreo marino.
 *
 * Exporta constantes geográficas (Bahía de Loreto) y parámetros de caché
 * reutilizados por todos los Route Handlers.
 */

// ─── Bahía de Loreto — Geografía ─────────────────────────────

/** Bounding box [west, south, east, north] for Bahía de Loreto. */
export const BAY_BBOX = {
  west: -111.5,
  south: 25.5,
  east: -110.5,
  north: 26.3,
} as const;

/** Central coordinates for point-based APIs (Open-Meteo). */
export const BAY_CENTER = {
  lat: 25.88,
  lng: -111.0,
} as const;

/**
 * WKT POLYGON covering Bahía de Loreto for the OBIS API.
 * Coordinates are lon lat pairs (GeoJSON order).
 */
export const BAY_POLYGON_WKT =
  "POLYGON((" +
  "-111.5 25.5," +
  "-110.5 25.5," +
  "-110.5 26.3," +
  "-111.5 26.3," +
  "-111.5 25.5" +
  "))";

// ─── External API URLs ──────────────────────────────────────

export const GFW_BASE_URL = "https://gateway.api.globalfishingwatch.org/v3";
export const OBIS_BASE_URL = "https://api.obis.org/v3";
export const OPEN_METEO_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine";
export const NOAA_TIDES_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter";

// ─── NOAA Station ────────────────────────────────────────────

/** Proxy tide station — Santa Rosalía, BCS. */
export const NOAA_STATION_ID = "9411406";

// ─── Cache / Revalidation (seconds) ─────────────────────────

/** 1 hour — used for intelligence & conditions. */
export const REVALIDATE_1H = 3600;

/** 12 hours — used for fishing-effort & tides. */
export const REVALIDATE_12H = 43200;

/** 24 hours — used for bay-health (OBIS data is slow-moving). */
export const REVALIDATE_24H = 86400;

// ─── Date Helpers ────────────────────────────────────────────

/** Returns an ISO date string N days in the past from now. */
export function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().split("T")[0];
}

/** Returns today's date as YYYY-MM-DD. */
export function todayISO(): string {
  return new Date().toISOString().split("T")[0];
}

/** Returns today's date as YYYYMMDD (NOAA format). */
export function todayCompact(): string {
  return todayISO().replace(/-/g, "");
}
