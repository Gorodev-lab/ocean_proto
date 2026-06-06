"use client";

import styles from "./LayerPanel.module.css";
import type { LayerCounts, LayerVisibility, LayerKey } from "@/types/ocean";

interface LayerDef {
  key: LayerKey;
  label: string;
  color: string;
  countKey: keyof LayerCounts;
  section?: string;
}

const LAYERS: LayerDef[] = [
  { key: "hotspots",  label: "Zonas de Riesgo",      color: "#FD8D3C", countKey: "hotspots"  },
  { key: "vessels",   label: "Embarcaciones AIS",     color: "#3b82f6", countKey: "vessels",   section: "TRÁFICO MARINO" },
  { key: "megafauna", label: "Megafauna",             color: "#44bbff", countKey: "megafauna" },
  { key: "platforms", label: "Cruceros & Megabarcos", color: "#a855f7", countKey: "platforms", section: "TIPOS DE FLOTA" },
  { key: "osvs",      label: "Pesca Industrial",      color: "#22c55e", countKey: "osvs"      },
  { key: "gaps",      label: "Apagones AIS",          color: "#facc15", countKey: "gaps"      },
];

interface LayerPanelProps {
  visibility: LayerVisibility;
  counts: LayerCounts;
  onToggle: (layer: LayerKey) => void;
}

export default function LayerPanel({ visibility, counts, onToggle }: LayerPanelProps) {
  return (
    <div className={styles.panel}>
      <h3 className={styles.title}>Capas</h3>
      {LAYERS.map((layer) => (
        <div key={layer.key}>
          {layer.section && (
            <div className={styles.sectionTitle}>{layer.section}</div>
          )}
          <label
            className={styles.item}
            style={{ "--layer-color": layer.color } as React.CSSProperties}
          >
            <input
              type="checkbox"
              className={styles.checkbox}
              checked={visibility[layer.key]}
              onChange={() => onToggle(layer.key)}
            />
            <span
              className={styles.dot}
              style={{ background: layer.color }}
            />
            <span className={styles.label}>{layer.label}</span>
            <span className={styles.count}>
              {counts[layer.countKey] > 0 ? counts[layer.countKey] : "—"}
            </span>
          </label>
        </div>
      ))}
    </div>
  );
}
