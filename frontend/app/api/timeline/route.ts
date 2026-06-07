/**
 * app/api/timeline/route.ts — Serie temporal mensual de detecciones.
 *
 * Fuente: Supabase RPC get_monthly_detections(year)
 * Incluye: vessels, megafauna, períodos de veda por especie,
 *          época de ballenas (Dic–Abr)
 */

import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

export const revalidate = 3600; // 1h

const MONTH_LABELS = [
  "Ene", "Feb", "Mar", "Abr", "May", "Jun",
  "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
];

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const year = parseInt(searchParams.get("year") ?? "2024", 10);

  const { data, error } = await supabase.rpc("get_monthly_detections", {
    p_year: year,
  });

  if (error || !data) {
    return NextResponse.json(
      { error: error?.message ?? "RPC failed", monthly: [] },
      { status: 500 }
    );
  }

  const monthly = (data as Array<{
    month: number;
    vessel_count: number;
    megafauna_count: number;
    dominant_species: string | null;
    is_whale_season: boolean;
    atun_veda_a: boolean;
    atun_veda_b: boolean;
    tiburon_veda: boolean;
    camaron_veda: boolean;
  }>).map((row) => ({
    month: row.month,
    label: MONTH_LABELS[row.month - 1],
    vessel_count: Number(row.vessel_count),
    megafauna_count: Number(row.megafauna_count),
    dominant_species: row.dominant_species,
    is_whale_season: row.is_whale_season,
    vedas: {
      atun_a: row.atun_veda_a,
      atun_b: row.atun_veda_b,
      tiburon: row.tiburon_veda,
      camaron: row.camaron_veda,
      any: row.atun_veda_a || row.atun_veda_b || row.tiburon_veda || row.camaron_veda,
    },
  }));

  // Peak detection month
  const peakVessels = monthly.reduce(
    (max, m) => (m.vessel_count > max.vessel_count ? m : max),
    monthly[0]
  );
  const peakMegafauna = monthly.reduce(
    (max, m) => (m.megafauna_count > max.megafauna_count ? m : max),
    monthly[0]
  );

  return NextResponse.json({
    generatedAt: new Date().toISOString(),
    year,
    monthly,
    summary: {
      total_vessel_detections: monthly.reduce((s, m) => s + m.vessel_count, 0),
      total_megafauna_sightings: monthly.reduce((s, m) => s + m.megafauna_count, 0),
      peak_vessel_month: peakVessels?.label,
      peak_megafauna_month: peakMegafauna?.label,
      whale_season_months: monthly.filter((m) => m.is_whale_season).map((m) => m.label),
    },
  });
}
