"use client";

import styles from "./StatsBar.module.css";

interface Stat {
  id: string;
  value: number | string;
  label: string;
  color: string;
}

interface StatsBarProps {
  vessels: number;
  megafauna: number;
  hotspots: number;
  maxRisk: number;
  platforms: number;
  gaps: number;
  kgNodes: number;
  kgEdges: number;
}

export default function StatsBar({
  vessels,
  megafauna,
  hotspots,
  maxRisk,
  platforms,
  gaps,
  kgNodes,
  kgEdges,
}: StatsBarProps) {
  const stats: Stat[] = [
    { id: "vessels",   value: vessels   || "—", label: "Emb. AIS",     color: "#3b82f6" },
    { id: "megafauna", value: megafauna || "—", label: "Avistamientos", color: "#44bbff" },
    { id: "hotspots",  value: hotspots  || "—", label: "Zonas Riesgo",  color: "#FD8D3C" },
    { id: "maxRisk",   value: maxRisk   || "—", label: "Max Risk",      color: "#ef4444" },
    { id: "platforms", value: platforms || "—", label: "Cruceros",      color: "#a855f7" },
    { id: "gaps",      value: gaps      || "—", label: "Apagones AIS",  color: "#facc15" },
    { id: "kgNodes",   value: kgNodes   || "—", label: "KG Nodos",      color: "var(--color-text-primary)" },
    { id: "kgEdges",   value: kgEdges   || "—", label: "KG Aristas",    color: "var(--color-text-secondary)" },
  ];

  return (
    <div className={styles.bar}>
      {stats.map((s) => (
        <div key={s.id} className={styles.card}>
          <div className={styles.value} style={{ color: s.color }}>
            {s.value}
          </div>
          <div className={styles.label}>{s.label}</div>
        </div>
      ))}
    </div>
  );
}
