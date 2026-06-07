/**
 * app/api/conflict-zones/route.ts — Zonas de conflicto vessel × megafauna.
 *
 * Fuente: Supabase RPC get_conflict_zones()
 * Retorna GeoJSON Feature Collection de celdas H3 con co-ocurrencia real.
 */

import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

export const revalidate = 3600; // 1h

export async function GET() {
  const { data, error } = await supabase.rpc("get_conflict_zones");

  if (error || !data) {
    return NextResponse.json(
      { error: error?.message ?? "RPC failed", zones: [], geojson: null },
      { status: 500 }
    );
  }

  type ConflictRow = {
    h3_index: string;
    ipa_100: number | null;
    conflict_level: string | null;
    vessel_count: number;
    megafauna_count: number;
    fishing_hours: number | null;
    score_cooccurrence: number | null;
    lat: number;
    lon: number;
  };

  const zones = data as ConflictRow[];

  // Build GeoJSON FeatureCollection (point-based for Leaflet)
  const geojson = {
    type: "FeatureCollection",
    features: zones.map((z) => ({
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [z.lon, z.lat],
      },
      properties: {
        h3_index: z.h3_index,
        ipa_100: z.ipa_100 ?? 0,
        conflict_level: z.conflict_level ?? "DESCONOCIDO",
        vessel_count: z.vessel_count,
        megafauna_count: z.megafauna_count,
        fishing_hours: z.fishing_hours ?? 0,
        score_cooccurrence: z.score_cooccurrence ?? 0,
      },
    })),
  };

  const topZone = zones[0];

  return NextResponse.json({
    generatedAt: new Date().toISOString(),
    total_conflict_zones: zones.length,
    top_zone: topZone
      ? {
          h3_index: topZone.h3_index,
          ipa_100: topZone.ipa_100,
          conflict_level: topZone.conflict_level,
          lat: topZone.lat,
          lon: topZone.lon,
        }
      : null,
    geojson,
  });
}
