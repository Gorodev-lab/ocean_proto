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
    { id: "vessels",   value: vessels   || "—", label: "Buques SAR",   color: "#ff8844" },
    { id: "megafauna", value: megafauna || "—", label: "Avistamientos", color: "#44bbff" },
    { id: "hotspots",  value: hotspots  || "—", label: "Zonas Riesgo",  color: "#ff4444" },
    { id: "maxRisk",   value: maxRisk   || "—", label: "Max Risk",      color: "#FEB24C" },
    { id: "platforms", value: platforms || "—", label: "Plataformas",   color: "#ff5577" },
    { id: "gaps",      value: gaps      || "—", label: "AIS Gaps",      color: "#ffdd44" },
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
