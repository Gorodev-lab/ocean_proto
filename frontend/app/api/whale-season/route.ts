/**
 * app/api/whale-season/route.ts — Estado de la época de ballenas.
 *
 * Fuente: Supabase RPC get_whale_season_stats()
 * Datos históricos: OBIS 2023-2024 (megafauna table)
 * Temporada: Diciembre – Abril (pico Febrero: 1,870 avistamientos)
 * Especie dominante: Megaptera novaeangliae (ballena jorobada)
 */

import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

export const revalidate = 3600;

export async function GET() {
  const { data, error } = await supabase.rpc("get_whale_season_stats");

  if (error || !data) {
    return NextResponse.json(
      { error: error?.message ?? "RPC failed" },
      { status: 500 }
    );
  }

  const stats = data as {
    is_active: boolean;
    current_month: number;
    peak_month: string;
    peak_sightings: number;
    dominant_species: string;
    season_months: string[];
    total_2024: number;
    total_2023: number;
    conflict_cells: number;
    atun_fleet_vms: number;
    atun_detections_vms: number;
    atun_fleet_ais: number;
    atun_detections_ais: number;
  };

  const currentMonth = stats.current_month;

  // Days to peak (February = month 2)
  const peakMonth = 2;
  let monthsToPeak = peakMonth - currentMonth;
  if (monthsToPeak < 0) monthsToPeak += 12;

  return NextResponse.json({
    generatedAt: new Date().toISOString(),
    is_active: stats.is_active,
    dominant_species: stats.dominant_species,
    common_name: "Ballena jorobada",
    season: {
      months: stats.season_months,
      peak_month: stats.peak_month,
      peak_sightings: stats.peak_sightings,
      months_to_peak: monthsToPeak,
    },
    historical: {
      total_2023: Number(stats.total_2023),
      total_2024: Number(stats.total_2024),
      trend: Number(stats.total_2024) > Number(stats.total_2023) ? "increasing" : "decreasing",
    },
    conflict: {
      cells_at_risk: Number(stats.conflict_cells),
    },
    tuna_fleet: {
      vms_detections: stats.atun_detections_vms,
      vms_vessels: stats.atun_fleet_vms,
      ais_detections: stats.atun_detections_ais,
      ais_vessels: stats.atun_fleet_ais,
    },
  });
}
