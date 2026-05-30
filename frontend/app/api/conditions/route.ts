/**
 * app/api/conditions/route.ts — Condiciones Marinas Actuales.
 *
 * Fuente: Open-Meteo Marine API (pública, sin token)
 * - Oleaje, periodo, viento, SST
 *
 * Cache: revalidate = 3600 (1 hora)
 */

import { NextResponse } from "next/server";
import { safeFetch } from "@/lib/vigia/fetcher";
import { classifyMarineCondition } from "@/lib/vigia/scoring";
import {
  OPEN_METEO_MARINE_URL,
  BAY_CENTER,
  REVALIDATE_1H,
} from "@/lib/vigia/config";
import type { ConditionsResponse } from "@/types/vigia";

// ─── Open-Meteo raw response shapes ─────────────────────────

interface OpenMeteoMarineResponse {
  current?: {
    wave_height?: number;
    wave_period?: number;
    wind_wave_height?: number;
    wind_wave_period?: number;
    swell_wave_height?: number;
    swell_wave_period?: number;
    wind_speed_10m?: number;
    [key: string]: unknown;
  };
  current_units?: Record<string, string>;
  hourly?: {
    time?: string[];
    wave_height?: number[];
    wave_period?: number[];
    wind_wave_height?: number[];
    wind_wave_period?: number[];
    swell_wave_height?: number[];
    swell_wave_period?: number[];
    sea_surface_temperature?: number[];
    wind_speed_10m?: number[];
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

// ─── Handler ─────────────────────────────────────────────────

export async function GET() {
  const params = new URLSearchParams({
    latitude: BAY_CENTER.lat.toString(),
    longitude: BAY_CENTER.lng.toString(),
    current: "wave_height,wave_period,wind_speed_10m,swell_wave_height,swell_wave_period",
    hourly: "sea_surface_temperature",
    forecast_days: "1",
    timezone: "America/Mazatlan",
  });

  const url = `${OPEN_METEO_MARINE_URL}?${params}`;

  const { data, error } = await safeFetch<OpenMeteoMarineResponse>(url, {
    revalidate: REVALIDATE_1H,
  });

  if (error || !data) {
    const degraded: ConditionsResponse = {
      generatedAt: new Date().toISOString(),
      waveHeight: 0,
      wavePeriod: 0,
      windSpeed: 0,
      seaSurfaceTemperature: null,
      condition: "Calm",
      status: {
        degraded: true,
        reason: error ?? "No data returned from Open-Meteo",
      },
    };
    return NextResponse.json(degraded);
  }

  // ── Extract current values ──────────────────────────────────

  const current = data.current;
  const waveHeight = current?.wave_height ?? current?.swell_wave_height ?? 0;
  const wavePeriod = current?.wave_period ?? current?.swell_wave_period ?? 0;
  const windSpeed = current?.wind_speed_10m ?? 0;

  // SST comes from hourly data — take the first available value
  const sstArray = data.hourly?.sea_surface_temperature;
  const seaSurfaceTemperature =
    sstArray && sstArray.length > 0 ? sstArray[0] : null;

  // ── Classify condition ──────────────────────────────────────

  const condition = classifyMarineCondition({
    waveHeight,
    wavePeriod,
    windSpeed,
  });

  const response: ConditionsResponse = {
    generatedAt: new Date().toISOString(),
    waveHeight: Math.round(waveHeight * 100) / 100,
    wavePeriod: Math.round(wavePeriod * 10) / 10,
    windSpeed: Math.round(windSpeed * 10) / 10,
    seaSurfaceTemperature:
      seaSurfaceTemperature !== null
        ? Math.round(seaSurfaceTemperature * 10) / 10
        : null,
    condition,
  };

  return NextResponse.json(response);
}
