/**
 * lib/vigia/scoring.ts — Funciones de cálculo para el pipeline de monitoreo.
 *
 * - Dark Vessel Score (composite 0–100)
 * - Marine Condition classification
 * - Fishing effort trend determination
 */

import type { MarineCondition, Trend, BayZone } from "@/types/vigia";

// ─── Dark Vessel Score ───────────────────────────────────────

/**
 * Weight configuration for the Dark Vessel composite score.
 *
 * - source     (30%): How the vessel was detected — SAR-only = highest risk
 * - proximity  (40%): Distance to the bay polygon — closer = higher risk
 * - recency    (20%): How recently the detection occurred
 * - recurrence (10%): How many times the same vessel has been detected
 */
const DVS_WEIGHTS = {
  source: 0.3,
  proximity: 0.4,
  recency: 0.2,
  recurrence: 0.1,
} as const;

interface DarkVesselScoreInput {
  /** Whether this detection was matched to an AIS signal. */
  matched: boolean;
  /** Distance in km from the bay polygon edge. Null = unknown (defaults to 50km). */
  proximityKm: number | null;
  /** Days since detection. */
  daysSinceDetection: number;
  /** Number of times this vessel has been detected in the area. */
  detectionCount: number;
}

/**
 * Calculates the Dark Vessel Score (0–100).
 *
 * Higher = more suspicious/risky.
 *
 * @example
 * const score = calculateDarkVesselScore({
 *   matched: false,
 *   proximityKm: 5,
 *   daysSinceDetection: 2,
 *   detectionCount: 3,
 * }); // → ~82
 */
export function calculateDarkVesselScore(input: DarkVesselScoreInput): number {
  // Source component: unmatched (no AIS) = 100, matched = 20
  const sourceScore = input.matched ? 20 : 100;

  // Proximity component: inverse distance, capped at 50km
  const distKm = input.proximityKm ?? 50;
  const proximityScore = Math.max(0, Math.min(100, (1 - distKm / 50) * 100));

  // Recency component: exponential decay over 90 days
  const recencyScore = Math.max(
    0,
    100 * Math.exp(-input.daysSinceDetection / 30)
  );

  // Recurrence component: logarithmic scale, capped at 10 detections
  const recurrenceScore = Math.min(
    100,
    (Math.log2(input.detectionCount + 1) / Math.log2(11)) * 100
  );

  const composite =
    DVS_WEIGHTS.source * sourceScore +
    DVS_WEIGHTS.proximity * proximityScore +
    DVS_WEIGHTS.recency * recencyScore +
    DVS_WEIGHTS.recurrence * recurrenceScore;

  return Math.round(Math.max(0, Math.min(100, composite)));
}

// ─── Marine Condition Classification ─────────────────────────

interface MarineConditionInput {
  /** Significant wave height in meters. */
  waveHeight: number;
  /** Wave period in seconds. */
  wavePeriod: number;
  /** Wind speed in m/s. */
  windSpeed: number;
}

/**
 * Classifies current marine conditions based on wave height, period, and wind.
 *
 * - Calm:   height < 0.5m
 * - Clean:  height ≥ 0.5m, period ≥ 10s, wind < 5 m/s
 * - Bumpy:  period < 10s OR wind ≥ 5 m/s
 * - Stormy: height > 2.5m
 */
export function classifyMarineCondition(
  input: MarineConditionInput
): MarineCondition {
  const { waveHeight, wavePeriod, windSpeed } = input;

  // Stormy takes precedence
  if (waveHeight > 2.5) return "Stormy";

  // Calm seas
  if (waveHeight < 0.5) return "Calm";

  // Clean: decent swell, light wind
  if (wavePeriod >= 10 && windSpeed < 5) return "Clean";

  // Everything else is choppy
  return "Bumpy";
}

// ─── Trend Determination ─────────────────────────────────────

/**
 * Compares current-period hours vs previous-period hours.
 * Returns the trend direction and the percentage change.
 *
 * A change within ±5% is considered "stable".
 */
export function determineTrend(
  currentHours: number,
  previousHours: number
): { trend: Trend; changePercent: number } {
  if (previousHours === 0) {
    return {
      trend: currentHours > 0 ? "up" : "stable",
      changePercent: currentHours > 0 ? 100 : 0,
    };
  }

  const changePercent =
    ((currentHours - previousHours) / previousHours) * 100;

  let trend: Trend;
  if (changePercent > 5) trend = "up";
  else if (changePercent < -5) trend = "down";
  else trend = "stable";

  return { trend, changePercent: Math.round(changePercent * 10) / 10 };
}

// ─── Bay Zone Assignment ─────────────────────────────────────

/**
 * Heuristic species → zone mapping for OBIS occurrences.
 *
 * Species commonly found in kelp forests or intertidal areas are mapped
 * to those zones; everything else defaults to "open_water".
 */
const KELP_SPECIES_KEYWORDS = [
  "kelp",
  "macrocystis",
  "eisenia",
  "sargassum",
  "holothuroidea",
  "asteroidea",
  "echinoidea",
  "strongylocentrotus",
  "haliotis",
  "panulirus",
];

const INTERTIDAL_SPECIES_KEYWORDS = [
  "intertidal",
  "littorina",
  "patella",
  "chiton",
  "grapsus",
  "pachygrapsus",
  "fiddler",
  "uca",
  "crassostrea",
  "mytilus",
  "balanus",
];

/**
 * Assigns a bay zone based on species name heuristics.
 * Falls back to "open_water" if no match is found.
 */
export function assignBayZone(scientificName: string): BayZone {
  const lower = scientificName.toLowerCase();

  if (INTERTIDAL_SPECIES_KEYWORDS.some((kw) => lower.includes(kw))) {
    return "intertidal";
  }

  if (KELP_SPECIES_KEYWORDS.some((kw) => lower.includes(kw))) {
    return "kelp_forest";
  }

  return "open_water";
}
