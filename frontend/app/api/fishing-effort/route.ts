/**
 * app/api/fishing-effort/route.ts — Esfuerzo Pesquero.
 *
 * Fuente: Global Fishing Watch API v3 (4Wings report)
 * - Esfuerzo pesquero aparente (30 días + 30 días anteriores para tendencia)
 *
 * Cache: revalidate = 43200 (12 horas)
 */

import { NextResponse } from "next/server";
import { safeFetch } from "@/lib/vigia/fetcher";
import { determineTrend } from "@/lib/vigia/scoring";
import {
  GFW_BASE_URL,
  BAY_BBOX,
  REVALIDATE_12H,
  daysAgo,
  todayISO,
} from "@/lib/vigia/config";
import type {
  FishingEffortResponse,
  FishingPoint,
  FlagBreakdown,
} from "@/types/vigia";

// ─── GFW raw response shapes ────────────────────────────────

interface GfwEffortEntry {
  lat?: number;
  lng?: number;
  longitude?: number;
  latitude?: number;
  flag?: string;
  hours?: number;
  fishingHours?: number;
  fishing_hours?: number;
  vessel_type?: string;
  [key: string]: unknown;
}

interface Gfw4WingsResponse {
  entries?: GfwEffortEntry[];
  [key: string]: unknown;
}

// ─── Helpers ─────────────────────────────────────────────────

function buildReportUrl(startDate: string, endDate: string): string {
  const { west, south, east, north } = BAY_BBOX;

  const region = JSON.stringify({
    type: "Polygon",
    coordinates: [
      [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
      ],
    ],
  });

  const params = new URLSearchParams({
    datasets: "public-global-fishing-effort:latest",
    "date-range": `${startDate},${endDate}`,
    "spatial-resolution": "HIGH",
    "temporal-resolution": "ENTIRE",
    format: "JSON",
    "region-source": "USER_JSON",
    region,
  });

  return `${GFW_BASE_URL}/4wings/report?${params}`;
}

function sumHours(entries: GfwEffortEntry[]): number {
  return entries.reduce(
    (sum, e) => sum + (e.hours ?? e.fishingHours ?? e.fishing_hours ?? 0),
    0
  );
}

// ─── Handler ─────────────────────────────────────────────────

export async function GET() {
  const today = todayISO();
  const thirtyDaysAgo = daysAgo(30);
  const sixtyDaysAgo = daysAgo(60);

  // Fetch current period (last 30 days) and previous period (30–60 days ago)
  const [currentResult, previousResult] = await Promise.all([
    safeFetch<Gfw4WingsResponse>(buildReportUrl(thirtyDaysAgo, today), {
      revalidate: REVALIDATE_12H,
    }),
    safeFetch<Gfw4WingsResponse>(buildReportUrl(sixtyDaysAgo, thirtyDaysAgo), {
      revalidate: REVALIDATE_12H,
    }),
  ]);

  // Both failed → degraded
  if (currentResult.error && previousResult.error) {
    const degraded: FishingEffortResponse = {
      generatedAt: new Date().toISOString(),
      totalHours: 0,
      byFlag: [],
      trend: "stable",
      changePercent: 0,
      points: [],
      status: {
        degraded: true,
        reason: `Current: ${currentResult.error}; Previous: ${previousResult.error}`,
      },
    };
    return NextResponse.json(degraded);
  }

  const currentEntries = currentResult.data?.entries ?? [];
  const previousEntries = previousResult.data?.entries ?? [];

  // ── Extract fishing points ──────────────────────────────────

  const points: FishingPoint[] = currentEntries.map((e) => ({
    lat: e.lat ?? e.latitude ?? 0,
    lng: e.lng ?? e.longitude ?? 0,
    hours: e.hours ?? e.fishingHours ?? e.fishing_hours ?? 0,
    flag: e.flag ?? null,
  }));

  // ── Aggregate by flag ───────────────────────────────────────

  const totalHours = sumHours(currentEntries);

  const flagMap: Record<string, number> = {};
  for (const entry of currentEntries) {
    const flag = entry.flag ?? "UNKNOWN";
    const hours = entry.hours ?? entry.fishingHours ?? entry.fishing_hours ?? 0;
    flagMap[flag] = (flagMap[flag] ?? 0) + hours;
  }

  const byFlag: FlagBreakdown[] = Object.entries(flagMap)
    .map(([flag, hours]) => ({
      flag,
      hours: Math.round(hours * 10) / 10,
      percentage:
        totalHours > 0 ? Math.round((hours / totalHours) * 1000) / 10 : 0,
    }))
    .sort((a, b) => b.hours - a.hours);

  // ── Trend vs previous period ────────────────────────────────

  const previousTotalHours = sumHours(previousEntries);
  const { trend, changePercent } = determineTrend(
    totalHours,
    previousTotalHours
  );

  // ── Assemble response ───────────────────────────────────────

  const response: FishingEffortResponse = {
    generatedAt: new Date().toISOString(),
    totalHours: Math.round(totalHours * 10) / 10,
    byFlag,
    trend,
    changePercent,
    points,
    ...(currentResult.error
      ? {
          status: {
            degraded: true,
            reason: `Partial data — previous period used for trend: ${currentResult.error}`,
          },
        }
      : {}),
  };

  return NextResponse.json(response);
}
