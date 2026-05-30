"use client";

import { useState, useEffect } from "react";
import { api, type KGStats } from "@/lib/api";
// KG stats still fetched from FastAPI (it's a compute endpoint, not a DB read)
import styles from "./KGPanel.module.css";

const KG_TYPE_META: Record<string, { label: string; cls: string }> = {
  HexCell:             { label: "HexCell",             cls: "low"    },
  VesselEvent:         { label: "VesselEvent",          cls: "med"    },
  VesselIdentity:      { label: "VesselIdentity",       cls: "med"    },
  MegafaunaOccurrence: { label: "MegafaunaOccurrence",  cls: "blue"   },
  Species:             { label: "Species",              cls: "blue"   },
  WhaleSpecies:        { label: "WhaleSpecies",         cls: "blue"   },
  OilPlatform:         { label: "OilPlatform",          cls: "red"    },
  SupportVessel:       { label: "SupportVessel",        cls: "pink"   },
  AisGapEvent:         { label: "AisGapEvent",          cls: "yellow" },
  RiskZone:            { label: "RiskZone",             cls: "high"   },
};

interface KGPanelProps {
  /** Notifica al padre los conteos de nodos/aristas para la StatsBar */
  onStats?: (nodes: number, edges: number) => void;
  /** Trigger desde fuera para re-fetch (ej: después de Build KG) */
  refreshTrigger?: number;
}

export default function KGPanel({ onStats, refreshTrigger }: KGPanelProps) {
  const [expanded, setExpanded] = useState(true);
  const [stats, setStats] = useState<KGStats | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStats = async () => {
    try {
      const data = await api.kgStats();
      setStats(data);
      onStats?.(data.nodes, data.edges);
    } catch {
      setStats(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchStats();
    const interval = setInterval(fetchStats, 60_000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshTrigger]);

  const isReady = stats?.status === "ready";

  const created = stats?.created
    ? new Date(stats.created).toLocaleString("es-MX", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

  return (
    <div className={`${styles.panel} ${expanded ? styles.expanded : styles.collapsed}`}>
      <div
        className={styles.panelHeader}
        onClick={() => setExpanded((e) => !e)}
        title="Colapsar / Expandir"
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && setExpanded((x) => !x)}
      >
        <h3 className={styles.title}>
          <span
            className={`${styles.dot} ${
              isReady ? styles.dotReady : loading ? styles.dotBuilding : ""
            }`}
          />
          Knowledge Graph
        </h3>
        <span className={styles.toggleIcon}>&#9660;</span>
      </div>

      <div className={styles.body}>
        {loading ? (
          <div className={styles.notReady}>Cargando estado del grafo...</div>
        ) : !isReady ? (
          <div className={styles.notReady}>
            Grafo no construido.
            <br />
            Usa <strong style={{ color: "var(--color-accent)" }}>⬡ Build KG</strong> para
            generarlo.
          </div>
        ) : (
          <>
            {Object.entries(KG_TYPE_META).map(([type, meta]) => {
              const cnt = stats?.node_types?.[type] ?? 0;
              if (cnt === 0) return null;
              return (
                <div key={type} className={styles.row}>
                  <span className={styles.rowType}>{meta.label}</span>
                  <span className={`${styles.count} ${styles[meta.cls] ?? ""}`}>
                    {cnt.toLocaleString()}
                  </span>
                </div>
              );
            })}
            <div className={styles.summary}>
              <span style={{ color: "#5a5f66" }}>generado</span>
              <span>{created}</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
