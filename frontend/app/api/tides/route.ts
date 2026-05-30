/**
 * app/api/tides/route.ts — Mareas Locales.
 *
 * Fuente: NOAA Tides and Currents API (pública, sin token)
 * - Predicciones de mareas altas y bajas del día actual
 *
 * Cache: revalidate = 43200 (12 horas)
 */

import { NextResponse } from "next/server";
import { safeFetch } from "@/lib/vigia/fetcher";
import {
  NOAA_TIDES_URL,
  NOAA_STATION_ID,
  REVALIDATE_12H,
  todayCompact,
} from "@/lib/vigia/config";
import type { TidesResponse, TidePrediction, TideType } from "@/types/vigia";

// ─── NOAA raw response shapes ───────────────────────────────

interface NoaaPrediction {
  t: string;   // "2026-05-29 06:42"
  v: string;   // "1.234" (feet)
  type?: string; // "H" or "L"
}

interface NoaaResponse {
  predictions?: NoaaPrediction[];
  error?: { message?: string };
  [key: string]: unknown;
}

// ─── Constants ───────────────────────────────────────────────

/** Convert feet to meters. */
const FT_TO_M = 0.3048;

// ─── Handler ─────────────────────────────────────────────────

export async function GET() {
  const today = todayCompact();

  // NOAA expects begin_date and end_date in YYYYMMDD format.
  // For "today" we fetch a 1-day window.
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const end = tomorrow.toISOString().split("T")[0].replace(/-/g, "");

  const params = new URLSearchParams({
    station: NOAA_STATION_ID,
    product: "predictions",
    datum: "MLLW",
    units: "english",      // feet — we convert to meters
    time_zone: "lst_ldt",  // local standard/daylight time
    format: "json",
    begin_date: today,
    end_date: end,
    interval: "hilo",      // only highs and lows
  });

  const url = `${NOAA_TIDES_URL}?${params}`;

  const { data, error } = await safeFetch<NoaaResponse>(url, {
    revalidate: REVALIDATE_12H,
  });

  if (error || !data || data.error) {
    const degraded: TidesResponse = {
      generatedAt: new Date().toISOString(),
      stationId: NOAA_STATION_ID,
      predictions: [],
      status: {
        degraded: true,
        reason:
          error ?? data?.error?.message ?? "No data returned from NOAA",
      },
    };
    return NextResponse.json(degraded);
  }

  // ── Filter and normalize predictions ────────────────────────

  const raw = data.predictions ?? [];

  const predictions: TidePrediction[] = raw
    .filter((p) => p.type === "H" || p.type === "L")
    .map((p) => {
      const heightFt = parseFloat(p.v) || 0;
      const heightM = Math.round(heightFt * FT_TO_M * 100) / 100;
      const type: TideType = p.type === "H" ? "High" : "Low";

      // Convert NOAA timestamp "YYYY-MM-DD HH:MM" to ISO-8601
      const isoTime = p.t.replace(" ", "T") + ":00";

      return {
        time: isoTime,
        height: heightM,
        type,
      };
    });

  const response: TidesResponse = {
    generatedAt: new Date().toISOString(),
    stationId: NOAA_STATION_ID,
    predictions,
  };

  return NextResponse.json(response);
}
