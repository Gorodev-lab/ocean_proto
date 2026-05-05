/**
 * types/ocean.ts — Tipos compartidos del dominio Ocean Proto.
 */

export interface InfoRow {
  key: string;
  val: string | number;
  cls?: string;
}

export interface InfoPanelState {
  visible: boolean;
  type: string;
  rows: InfoRow[];
}

export interface LayerCounts {
  hotspots: number;
  vessels: number;
  megafauna: number;
  platforms: number;
  osvs: number;
  gaps: number;
}

export interface LayerVisibility {
  hotspots: boolean;
  vessels: boolean;
  megafauna: boolean;
  platforms: boolean;
  osvs: boolean;
  gaps: boolean;
}

export type LayerKey = keyof LayerVisibility;
