/**
 * app/api/bay-health/route.ts — Salud de la Bahía / Biodiversidad.
 *
 * Fuente: OBIS (Ocean Biodiversity Information System) REST API v3
 * - Registros de ocurrencia de especies en el polígono de la bahía
 *
 * Cache: revalidate = 86400 (24 horas)
 */

import { NextResponse } from "next/server";
import { safeFetch } from "@/lib/vigia/fetcher";
import { assignBayZone } from "@/lib/vigia/scoring";
import {
  OBIS_BASE_URL,
  BAY_POLYGON_WKT,
  REVALIDATE_24H,
} from "@/lib/vigia/config";
import type { BayHealthResponse, SpeciesOccurrence } from "@/types/vigia";

// ─── OBIS raw response shapes ───────────────────────────────

interface ObisOccurrence {
  scientificName?: string;
  vernacularName?: string;
  eventDate?: string;
  date_mid?: number;
  decimalLatitude?: number;
  decimalLongitude?: number;
  catalogNumber?: string;
  occurrenceID?: string;
  [key: string]: unknown;
}

interface ObisResponse {
  total?: number;
  results?: ObisOccurrence[];
  [key: string]: unknown;
}

// ─── Handler ─────────────────────────────────────────────────

export async function GET() {
  const params = new URLSearchParams({
    geometry: BAY_POLYGON_WKT,
    size: "500",
  });

  const url = `${OBIS_BASE_URL}/occurrence?${params}`;

  const { data, error } = await safeFetch<ObisResponse>(url, {
    revalidate: REVALIDATE_24H,
  });

  if (error || !data) {
    const degraded: BayHealthResponse = {
      generatedAt: new Date().toISOString(),
      totalRecords: 0,
      uniqueSpecies: 0,
      occurrences: [],
      status: {
        degraded: true,
        reason: error ?? "No data returned from OBIS",
      },
    };
    return NextResponse.json(degraded);
  }

  // ── Normalize records ───────────────────────────────────────

  const results = data.results ?? [];

  const occurrences: SpeciesOccurrence[] = results
    .filter((r) => r.scientificName)
    .map((r) => {
      const scientificName = r.scientificName ?? "Unknown";
      let dateStr: string | null = null;

      if (r.eventDate) {
        dateStr = r.eventDate;
      } else if (r.date_mid) {
        // OBIS returns date_mid as epoch milliseconds
        dateStr = new Date(r.date_mid).toISOString().split("T")[0];
      }

      return {
        scientificName,
        vernacularName: r.vernacularName ?? null,
        date: dateStr,
        lat: r.decimalLatitude ?? 0,
        lng: r.decimalLongitude ?? 0,
        catalogNumber: r.catalogNumber ?? r.occurrenceID ?? null,
        zone: assignBayZone(scientificName),
      };
    });

  // ── Count unique species ────────────────────────────────────

  const speciesSet = new Set(occurrences.map((o) => o.scientificName));

  const response: BayHealthResponse = {
    generatedAt: new Date().toISOString(),
    totalRecords: data.total ?? occurrences.length,
    uniqueSpecies: speciesSet.size,
    occurrences,
  };

  return NextResponse.json(response);
}
