/**
 * types/vigia.ts — Tipos del pipeline de monitoreo marino (Vigía).
 *
 * Define las interfaces de respuesta para los 5 Route Handlers del sistema
 * de monitoreo: intelligence, fishing-effort, bay-health, conditions, tides.
 */

// ─── Shared ──────────────────────────────────────────────────

/** Standard degraded response when an upstream API fails. */
export interface DegradedStatus {
  degraded: boolean;
  reason?: string;
}

// ─── /api/intelligence ───────────────────────────────────────

export interface VesselGroup {
  label: string;
  count: number;
  /** Total presence hours aggregated for this group. */
  presenceHours: number;
}

export interface DarkVessel {
  id: string;
  lat: number;
  lng: number;
  /** ISO-8601 timestamp of the SAR detection. */
  detectedAt: string;
  /** Whether this detection was matched to an AIS signal. */
  matched: boolean;
  /** Composite score 0–100 calculated from source/proximity/recency/recurrence. */
  score: number;
  /** Distance in km to the nearest bay polygon edge. */
  proximityKm: number | null;
}

export interface NotableVessel {
  id: string;
  name: string | null;
  flag: string | null;
  vesselClass: string | null;
  /** Total hours of presence in the bounding box. */
  presenceHours: number;
}

export interface IntelligenceResponse {
  /** Timestamp of when this payload was generated (ISO-8601). */
  generatedAt: string;
  totalVessels: number;
  byClass: VesselGroup[];
  byFlag: VesselGroup[];
  /** Top vessels by presence hours. */
  notableVessels: NotableVessel[];
  darkVessels: DarkVessel[];
  /** Average dark-vessel score across all SAR detections. */
  avgDarkScore: number;
  status?: DegradedStatus;
}

// ─── /api/fishing-effort ─────────────────────────────────────

export interface FishingPoint {
  lat: number;
  lng: number;
  /** Apparent fishing hours at this cell. */
  hours: number;
  flag: string | null;
}

export interface FlagBreakdown {
  flag: string;
  hours: number;
  percentage: number;
}

export type Trend = "up" | "down" | "stable";

export interface FishingEffortResponse {
  generatedAt: string;
  totalHours: number;
  /** Breakdown of effort by flag state. */
  byFlag: FlagBreakdown[];
  /** Trend compared to the previous period. */
  trend: Trend;
  /** Change percentage vs previous period (negative = down). */
  changePercent: number;
  points: FishingPoint[];
  status?: DegradedStatus;
}

// ─── /api/bay-health ─────────────────────────────────────────

export type BayZone = "open_water" | "kelp_forest" | "intertidal";

export interface SpeciesOccurrence {
  scientificName: string;
  vernacularName: string | null;
  date: string | null;
  lat: number;
  lng: number;
  catalogNumber: string | null;
  zone: BayZone;
}

export interface BayHealthResponse {
  generatedAt: string;
  totalRecords: number;
  uniqueSpecies: number;
  occurrences: SpeciesOccurrence[];
  status?: DegradedStatus;
}

// ─── /api/conditions ─────────────────────────────────────────

export type MarineCondition = "Calm" | "Clean" | "Bumpy" | "Stormy";

export interface ConditionsResponse {
  generatedAt: string;
  /** Significant wave height in meters. */
  waveHeight: number;
  /** Wave period in seconds. */
  wavePeriod: number;
  /** Wind speed in m/s at 10m above sea level. */
  windSpeed: number;
  /** Sea-surface temperature in °C. */
  seaSurfaceTemperature: number | null;
  /** Classified condition string. */
  condition: MarineCondition;
  status?: DegradedStatus;
}

// ─── /api/tides ──────────────────────────────────────────────

export type TideType = "High" | "Low";

export interface TidePrediction {
  /** ISO-8601 datetime of the predicted tide. */
  time: string;
  /** Water level height in meters relative to MLLW datum. */
  height: number;
  type: TideType;
}

export interface TidesResponse {
  generatedAt: string;
  stationId: string;
  /** Tide predictions for today (High and Low only). */
  predictions: TidePrediction[];
  status?: DegradedStatus;
}
