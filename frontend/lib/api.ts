/**
 * lib/api.ts — Cliente tipado para el backend FastAPI de Ocean Proto.
 */

export interface GeoJSONFeatureCollection {
  type: "FeatureCollection";
  features: GeoJSONFeature[];
}

export interface GeoJSONFeature {
  type: "Feature";
  geometry: {
    type: string;
    coordinates: number[] | number[][];
  };
  properties: Record<string, unknown>;
}

export interface KGStats {
  status: "ready" | "not_built";
  nodes: number;
  edges: number;
  node_types: Record<string, number>;
  graph_name?: string;
  created?: string;
}

export interface SpeciesRecord {
  species: string;
  taxa_group: string | null;
  oil_relevance: string | null;
  count: number;
  pct_of_total: number;
}

export interface SpeciesResponse {
  total_records: number;
  total_species: number;
  species: SpeciesRecord[];
}

const BASE = "/api";
const EMPTY_FC: GeoJSONFeatureCollection = { type: "FeatureCollection", features: [] };

async function fetchJSON<T>(path: string, fallback: T, init?: RequestInit): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, init);
    if (!res.ok) {
      console.warn(`[Ocean API] ${path} → ${res.status}`);
      return fallback;
    }
    return (await res.json()) as T;
  } catch {
    // Backend not running — silently degrade
    return fallback;
  }
}

export const api = {
  hotspots: () => fetchJSON<GeoJSONFeatureCollection>("/risk-hotspots", EMPTY_FC),
  vessels: () => fetchJSON<GeoJSONFeatureCollection>("/vessels", EMPTY_FC),
  megafauna: () => fetchJSON<GeoJSONFeatureCollection>("/megafauna/", EMPTY_FC),
  platforms: () => fetchJSON<GeoJSONFeatureCollection>("/oil-platforms", EMPTY_FC),
  osvs: () => fetchJSON<GeoJSONFeatureCollection>("/support-vessels", EMPTY_FC),
  gaps: () => fetchJSON<GeoJSONFeatureCollection>("/gap-events", EMPTY_FC),
  kgStats: () =>
    fetchJSON<KGStats>("/graph/stats", {
      status: "not_built",
      nodes: 0,
      edges: 0,
      node_types: {},
    }),
  megafaunaSpecies: () =>
    fetchJSON<SpeciesResponse>("/megafauna/species", {
      total_records: 0,
      total_species: 0,
      species: [],
    }),
  refresh: (buildKg = false) =>
    fetchJSON<{ status: string; message: string }>(
      `/refresh?build_kg=${buildKg}`,
      { status: "error", message: "Backend not available" },
      { method: "POST" }
    ),
};

/** Helpers de color — se usan en el mapa y en los paneles */
export function getRiskColor(score: number): string {
  return score > 20
    ? "#800026"
    : score > 15
    ? "#BD0026"
    : score > 10
    ? "#E31A1C"
    : score > 5
    ? "#FC4E2A"
    : score > 2
    ? "#FD8D3C"
    : score > 0
    ? "#FEB24C"
    : "#FFEDA0";
}

export function getRiskClass(score: number): string {
  if (score > 10) return "risk-high";
  if (score > 3) return "risk-med";
  return "risk-low";
}

export const VESSEL_COLORS: Record<string, string> = {
  passenger:      "#a855f7",   // Cruceros / Yates — violeta
  cargo:          "#f59e0b",   // Carga general — ámbar
  fishing:        "#22c55e",   // Pesca industrial — verde
  seismic_vessel: "#ef4444",   // Buque sísmico — rojo
  noisy_vessel:   "#f97316",   // Buque ruidoso — naranja
  other:          "#94a3b8",   // Otro — gris
  unmatched:      "#475569",   // Sin clasificar — gris oscuro
};

export const SPECIES_COLORS: Record<string, string> = {
  "Megaptera novaeangliae": "#44bbff",
  "Balaenoptera musculus": "#2299ff",
  "Rhincodon typus": "#00ddaa",
  "Eschrichtius robustus": "#66aaff",
  "Balaenoptera physalus": "#3388dd",
  "Physeter macrocephalus": "#88aaff",
  "Balaenoptera borealis": "#5599ee",
};
