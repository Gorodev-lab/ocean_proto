/**
 * lib/supabase.ts — Supabase client + GeoJSON builders para Ocean Proto.
 *
 * Env vars requeridas (Vercel Dashboard o .env.local):
 *   NEXT_PUBLIC_SUPABASE_URL
 *   NEXT_PUBLIC_SUPABASE_ANON_KEY
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// ── Client singleton ─────────────────────────────────────────
const supabaseUrl  = process.env.NEXT_PUBLIC_SUPABASE_URL  ?? "";
const supabaseAnon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

// Prevent runtime crash at import time if environment variables are not set.
// A mock Proxy client is returned to allow the rest of the application to render.
export const supabase: SupabaseClient = (supabaseUrl && supabaseAnon)
  ? createClient(supabaseUrl, supabaseAnon)
  : new Proxy({} as any, {
      get(target, prop) {
        console.warn(`[Supabase Client] Environment variables NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY are missing. Prop "${String(prop)}" accessed.`);
        return () => Promise.resolve({ data: null, error: { message: "Supabase client not initialized (missing environment variables)." } });
      }
    }) as unknown as SupabaseClient;


// ── Re-export GeoJSON types & helpers from api.ts ────────────
export type { GeoJSONFeatureCollection, GeoJSONFeature } from "./api";
export { getRiskColor, getRiskClass, VESSEL_COLORS, SPECIES_COLORS } from "./api";

// ── Shared empty fallback ────────────────────────────────────
import type { GeoJSONFeatureCollection } from "./api";
const EMPTY_FC: GeoJSONFeatureCollection = { type: "FeatureCollection", features: [] };

function toFC(features: GeoJSONFeatureCollection["features"]): GeoJSONFeatureCollection {
  return { type: "FeatureCollection", features };
}

// ── Helpers to convert Supabase rows → GeoJSON features ─────

// function parsePoint(geom: string | null): [number, number] | null {
//   if (!geom) return null;
//   // PostgREST returns geometry as WKT: "0101000020E6100000..."
//   // or as GeoJSON if we use ?select=geom::text
//   // We'll use lon/lat columns as fallback
//   return null;
// }

// ── API — queries Supabase PostgREST ────────────────────────

export const db = {
  /** Risk hotspots: returns all H3 hexagons with IPA scores */
  async hotspots(): Promise<GeoJSONFeatureCollection> {
    const { data, error } = await supabase.rpc("get_risk_hotspots_geojson");
    if (error) {
      console.warn("[Supabase] hotspots:", error.message);
      return EMPTY_FC;
    }
    return (data as GeoJSONFeatureCollection) ?? EMPTY_FC;
  },

  /** Vessels: SAR/AIS detections as point features */
  async vessels(): Promise<GeoJSONFeatureCollection> {
    const { data, error } = await supabase
      .from("vessels")
      .select("mmsi, vessel_type, detected_at, geom")
      .limit(2000);
    if (error) { console.warn("[Supabase] vessels:", error.message); return EMPTY_FC; }
    if (!data) return EMPTY_FC;

    const features = data
      .filter((r) => r.geom)
      .map((r) => {
        const g = typeof r.geom === "string" ? JSON.parse(r.geom) : r.geom;
        return {
          type: "Feature" as const,
          geometry: g,
          properties: { mmsi: r.mmsi, vessel_type: r.vessel_type, timestamp: r.detected_at },
        };
      });
    return toFC(features);
  },

  /** Megafauna: OBIS cetacean occurrences */
  async megafauna(): Promise<GeoJSONFeatureCollection> {
    const { data, error } = await supabase
      .from("megafauna")
      .select("species, taxa_group, oil_relevance, observed_at, geom")
      .limit(5000);
    if (error) { console.warn("[Supabase] megafauna:", error.message); return EMPTY_FC; }
    if (!data) return EMPTY_FC;

    const features = data
      .filter((r) => r.geom)
      .map((r) => {
        const g = typeof r.geom === "string" ? JSON.parse(r.geom) : r.geom;
        return {
          type: "Feature" as const,
          geometry: g,
          properties: { species: r.species, taxa_group: r.taxa_group, oil_relevance: r.oil_relevance, timestamp: r.observed_at },
        };
      });
    return toFC(features);
  },

  /** Oil platforms */
  async platforms(): Promise<GeoJSONFeatureCollection> {
    const { data, error } = await supabase
      .from("oil_platforms")
      .select("platform_id, category, label, source, geom");
    if (error) { console.warn("[Supabase] platforms:", error.message); return EMPTY_FC; }
    if (!data) return EMPTY_FC;

    const features = data
      .filter((r) => r.geom)
      .map((r) => {
        const g = typeof r.geom === "string" ? JSON.parse(r.geom) : r.geom;
        return {
          type: "Feature" as const,
          geometry: g,
          properties: { platform_id: r.platform_id, category: r.category, label: r.label, source: r.source },
        };
      });
    return toFC(features);
  },

  /** Support vessels (OSVs) */
  async osvs(): Promise<GeoJSONFeatureCollection> {
    const { data, error } = await supabase
      .from("support_vessels")
      .select("mmsi, shipname, flag, vessel_type, geom");
    if (error) { console.warn("[Supabase] osvs:", error.message); return EMPTY_FC; }
    if (!data) return EMPTY_FC;

    const features = data
      .filter((r) => r.geom)
      .map((r) => {
        const g = typeof r.geom === "string" ? JSON.parse(r.geom) : r.geom;
        return {
          type: "Feature" as const,
          geometry: g,
          properties: { mmsi: r.mmsi, shipname: r.shipname, flag: r.flag, vessel_type: r.vessel_type },
        };
      });
    return toFC(features);
  },

  /** AIS gap events */
  async gaps(): Promise<GeoJSONFeatureCollection> {
    const { data, error } = await supabase
      .from("gap_events")
      .select("mmsi, shipname, flag, gap_hours, gap_start, gap_end, geom")
      .limit(1000);
    if (error) { console.warn("[Supabase] gaps:", error.message); return EMPTY_FC; }
    if (!data) return EMPTY_FC;

    const features = data
      .filter((r) => r.geom)
      .map((r) => {
        const g = typeof r.geom === "string" ? JSON.parse(r.geom) : r.geom;
        return {
          type: "Feature" as const,
          geometry: g,
          properties: { mmsi: r.mmsi, shipname: r.shipname, flag: r.flag, gap_hours: r.gap_hours, start: r.gap_start, end: r.gap_end },
        };
      });
    return toFC(features);
  },

  /** KG stats — fetched directly from Supabase knowledge_graph table */
  async kgStats() {
    const { data, error } = await supabase
      .from("knowledge_graph")
      .select("data")
      .eq("graph_name", "OceanProto Knowledge Graph")
      .maybeSingle();

    if (error) {
      console.warn("[Supabase] kgStats:", error.message);
      return { status: "not_built" as const, nodes: 0, edges: 0, node_types: {} };
    }
    if (!data || !data.data) {
      return { status: "not_built" as const, nodes: 0, edges: 0, node_types: {} };
    }

    const graphData = data.data as any;
    const nodes = graphData.nodes ?? [];
    const links = graphData.links ?? [];
    const node_types: Record<string, number> = {};
    nodes.forEach((n: any) => {
      const t = n.type || "Unknown";
      node_types[t] = (node_types[t] || 0) + 1;
    });

    return {
      status: "ready" as const,
      nodes: nodes.length,
      edges: links.length,
      node_types,
      graph_name: graphData.graph?.name ?? "OceanProto Knowledge Graph",
      created: graphData.graph?.created ?? "",
    };
  },

  /** Knowledge Graph: returns the full graph JSON from Supabase */
  async knowledgeGraph(): Promise<any> {
    const { data, error } = await supabase
      .from("knowledge_graph")
      .select("data")
      .eq("graph_name", "OceanProto Knowledge Graph")
      .maybeSingle();

    if (error) {
      console.warn("[Supabase] knowledgeGraph:", error.message);
      return { nodes: [], links: [] };
    }
    return data?.data ?? { nodes: [], links: [] };
  },
};
