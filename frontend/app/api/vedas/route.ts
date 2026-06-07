/**
 * app/api/vedas/route.ts — Vedas de pesca activas y próximas.
 *
 * Fuente: Supabase RPC get_active_vedas()
 * Datos: NOM-235/IATTC (atún), NOM-029-PESC-2006 (tiburón/manta),
 *        NOM-002-SAG/PESC-2013 (camarón)
 *
 * Cache: 24h — los períodos de veda cambian estacionalmente
 */

import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

export const revalidate = 86400; // 24h

const MONTH_NAMES = [
  "", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
  "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
];

const SPECIES_CODE: Record<string, string> = {
  "atún":       "THN",    // Thunnus
  "tiburón":    "SEL",    // Selachii
  "camarón":    "PEN",    // Penaeidae
  "totoaba":    "TOT",    // Totoaba macdonaldi
  "manta_raya": "MOB",    // Mobulidae
};

export async function GET() {
  const currentMonth = new Date().getMonth() + 1; // 1-12

  // Active vedas this month
  const { data: active, error: e1 } = await supabase.rpc("get_active_vedas", {
    p_mes: currentMonth,
  });

  // Upcoming vedas next 2 months
  const nextMonth = currentMonth === 12 ? 1 : currentMonth + 1;
  const { data: upcoming, error: e2 } = await supabase.rpc("get_active_vedas", {
    p_mes: nextMonth,
  });

  if (e1 || e2) {
    return NextResponse.json(
      { active: [], upcoming: [], error: e1?.message ?? e2?.message },
      { status: 500 }
    );
  }

  const fmt = (v: {
    nombre: string;
    especie_obj: string;
    arte_pesca: string | null;
    tipo: string;
    mes_inicio: number | null;
    mes_fin: number | null;
    norma: string | null;
    notas: string | null;
  }) => ({
    nombre: v.nombre,
    especie: v.especie_obj,
    arte_pesca: v.arte_pesca,
    tipo: v.tipo,
    periodo:
      v.tipo === "permanente"
        ? "Permanente"
        : v.mes_inicio && v.mes_fin
        ? `${MONTH_NAMES[v.mes_inicio]} – ${MONTH_NAMES[v.mes_fin]}`
        : null,
    norma: v.norma,
    notas: v.notas,
    code: SPECIES_CODE[v.especie_obj] ?? "UNK",
  });

  return NextResponse.json({
    generatedAt: new Date().toISOString(),
    currentMonth,
    active: (active ?? []).map(fmt),
    upcoming: (upcoming ?? [])
      .filter(
        (u: { nombre: string }) =>
          !(active ?? []).find(
            (a: { nombre: string }) => a.nombre === u.nombre
          )
      )
      .map(fmt),
  });
}
