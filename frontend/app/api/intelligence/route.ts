/**
 * app/api/intelligence/route.ts — Inteligencia de Embarcaciones.
 *
 * Fuente: Global Fishing Watch API v3
 * - Presencia de embarcaciones (90 días)
 * - Detecciones SAR de dark vessels (90 días)
 *
 * Cache: revalidate = 3600 (1 hora)
 */

import { NextResponse } from "next/server";
import { safeFetch } from "@/lib/vigia/fetcher";
import { calculateDarkVesselScore } from "@/lib/vigia/scoring";
import {
  GFW_BASE_URL,
  BAY_BBOX,
  REVALIDATE_1H,
  daysAgo,
} from "@/lib/vigia/config";
import type {
  IntelligenceResponse,
  VesselGroup,
  DarkVessel,
  NotableVessel,
} from "@/types/vigia";

// ─── GFW raw response shapes ────────────────────────────────

interface GfwPresenceEntry {
  id?: string;
  vesselId?: string;
  name?: string;
  flag?: string;
  vesselType?: string;
  vessel_type?: string;
  hours?: number;
  presenceHours?: number;
  [key: string]: unknown;
}

interface GfwPresenceResponse {
  entries?: GfwPresenceEntry[];
  total?: number;
  [key: string]: unknown;
}

interface GfwSarDetection {
  id?: string;
  lat?: number;
  lng?: number;
  position?: { lat?: number; lon?: number };
  start?: string;
  timestamp?: string;
  matched?: boolean;
  matchedVessel?: unknown;
  [key: string]: unknown;
}

interface GfwEventsResponse {
  entries?: GfwSarDetection[];
  events?: GfwSarDetection[];
  total?: number;
  [key: string]: unknown;
}

// ─── Helpers ─────────────────────────────────────────────────

function groupBy<T>(
  items: T[],
  keyFn: (item: T) => string
): Record<string, T[]> {
  const map: Record<string, T[]> = {};
  for (const item of items) {
    const key = keyFn(item);
    (map[key] ??= []).push(item);
  }
  return map;
}

function toVesselGroups(
  entries: GfwPresenceEntry[],
  keyFn: (e: GfwPresenceEntry) => string
): VesselGroup[] {
  const grouped = groupBy(entries, keyFn);
  return Object.entries(grouped).map(([label, items]) => ({
    label,
    count: items.length,
    presenceHours: items.reduce(
      (sum, e) => sum + (e.hours ?? e.presenceHours ?? 0),
      0
    ),
  }));
}

// ─── Handler ─────────────────────────────────────────────────

export async function GET() {
  const startDate = daysAgo(90);
  const { west, south, east, north } = BAY_BBOX;
  const bbox = `${west},${south},${east},${north}`;

  // 1. Fetch presence data
  const presenceUrl =
    `${GFW_BASE_URL}/4wings/report?` +
    new URLSearchParams({
      datasets: "public-global-fishing-effort:latest",
      "date-range": `${startDate},${new Date().toISOString().split("T")[0]}`,
      "spatial-resolution": "LOW",
      "temporal-resolution": "ENTIRE",
      format: "JSON",
      "region-source": "USER_JSON",
      region: JSON.stringify({
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
      }),
    });

  // 2. Fetch SAR dark-vessel detections
  const sarUrl =
    `${GFW_BASE_URL}/events?` +
    new URLSearchParams({
      datasets: "public-global-sar-detections:latest",
      "start-date": startDate,
      "end-date": new Date().toISOString().split("T")[0],
      "geometry.bbox": bbox,
      limit: "500",
    });

  const [presenceResult, sarResult] = await Promise.all([
    safeFetch<GfwPresenceResponse>(presenceUrl, { revalidate: REVALIDATE_1H }),
    safeFetch<GfwEventsResponse>(sarUrl, { revalidate: REVALIDATE_1H }),
  ]);

  // Build degraded response if both fail
  if (presenceResult.error && sarResult.error) {
    const degraded: IntelligenceResponse = {
      generatedAt: new Date().toISOString(),
      totalVessels: 0,
      byClass: [],
      byFlag: [],
      notableVessels: [],
      darkVessels: [],
      avgDarkScore: 0,
      status: {
        degraded: true,
        reason: `Presence: ${presenceResult.error}; SAR: ${sarResult.error}`,
      },
    };
    return NextResponse.json(degraded);
  }

  // ── Process presence ────────────────────────────────────────

  const entries = presenceResult.data?.entries ?? [];

  const byClass = toVesselGroups(
    entries,
    (e) => e.vesselType ?? e.vessel_type ?? "all"
  );

  const byFlag = toVesselGroups(entries, (e) => e.flag ?? "UNKNOWN");

  // Notable vessels: top 10 by presence hours
  const sortedByHours = [...entries].sort(
    (a, b) => (b.hours ?? b.presenceHours ?? 0) - (a.hours ?? a.presenceHours ?? 0)
  );
  const notableVessels: NotableVessel[] = sortedByHours
    .slice(0, 10)
    .map((e) => ({
      id: e.id ?? e.vesselId ?? "unknown",
      name: e.name ?? null,
      flag: e.flag ?? null,
      vesselClass: e.vesselType ?? e.vessel_type ?? null,
      presenceHours: e.hours ?? e.presenceHours ?? 0,
    }));

  // ── Process SAR detections ──────────────────────────────────

  const rawDetections = sarResult.data?.entries ?? sarResult.data?.events ?? [];
  const now = Date.now();

  const darkVessels: DarkVessel[] = rawDetections.map((d) => {
    const lat = d.lat ?? d.position?.lat ?? 0;
    const lng = d.lng ?? d.position?.lon ?? 0;
    const detectedAt = d.start ?? d.timestamp ?? new Date().toISOString();
    const matched = d.matched ?? !!d.matchedVessel;
    const daysSince = Math.max(
      0,
      (now - new Date(detectedAt).getTime()) / 86_400_000
    );

    // Approximate proximity to bay center
    const centerLat = (south + north) / 2;
    const centerLng = (west + east) / 2;
    const distDeg = Math.sqrt(
      (lat - centerLat) ** 2 + (lng - centerLng) ** 2
    );
    const proximityKm = Math.round(distDeg * 111); // rough km

    const score = calculateDarkVesselScore({
      matched,
      proximityKm,
      daysSinceDetection: daysSince,
      detectionCount: 1, // single detection context
    });

    return {
      id: d.id ?? `sar-${lat}-${lng}`,
      lat,
      lng,
      detectedAt,
      matched,
      score,
      proximityKm,
    };
  });

  const avgDarkScore =
    darkVessels.length > 0
      ? Math.round(
          darkVessels.reduce((sum, v) => sum + v.score, 0) /
            darkVessels.length
        )
      : 0;

  // ── Assemble response ───────────────────────────────────────

  const response: IntelligenceResponse = {
    generatedAt: new Date().toISOString(),
    totalVessels: entries.length,
    byClass,
    byFlag,
    notableVessels,
    darkVessels,
    avgDarkScore,
    ...(presenceResult.error || sarResult.error
      ? {
          status: {
            degraded: true,
            reason: presenceResult.error ?? sarResult.error ?? undefined,
          },
        }
      : {}),
  };

  return NextResponse.json(response);
}
