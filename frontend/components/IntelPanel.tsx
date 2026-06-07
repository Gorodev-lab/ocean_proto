"use client";

import { useState, useEffect } from "react";
import { supabase } from "@/lib/supabase";
import styles from "./IntelPanel.module.css";

// ── Types ────────────────────────────────────────────────────────────────────

interface VesselClass {
  vessel_type: string;
  count: number;
}

interface TopVessel {
  mmsi: string;
  vessel_type: string;
  detections: number;
}

interface VesselIntel {
  total_vessels: number;
  dark_events: number;
  date_from: string | null;
  date_to: string | null;
  by_class: VesselClass[];
  top_vessels: TopVessel[];
}

interface SpeciesRecord {
  species: string;
  taxa_group: string;
  count: number;
}

interface YearRecord {
  year: number;
  species: string;
  count: number;
}

interface BayHealth {
  total_records: number;
  date_from: string | null;
  date_to: string | null;
  by_species: SpeciesRecord[];
  by_year_species: YearRecord[];
}

// ── Metadata ─────────────────────────────────────────────────────────────────

const VESSEL_LABELS: Record<string, { label: string; color: string }> = {
  unmatched:      { label: "Sin clasificar",    color: "#475569" },
  other:          { label: "Otro",              color: "#94a3b8" },
  cargo:          { label: "Carga General",     color: "#f59e0b" },
  passenger:      { label: "Cruceros / Yates",  color: "#a855f7" },
  fishing:        { label: "Pesca Industrial",  color: "#22c55e" },
  seismic_vessel: { label: "Buque Sísmico",     color: "#ef4444" },
  noisy_vessel:   { label: "Buque Ruidoso",     color: "#f97316" },
};

const SPECIES_LABELS: Record<string, { label: string; latin: string; color: string; sym: string }> = {
  "Megaptera novaeangliae": { label: "Ballena Jorobada",    latin: "M. novaeangliae",   color: "#22d3ee", sym: "Mn" },
  "Balaenoptera musculus":  { label: "Ballena Azul",        latin: "B. musculus",        color: "#818cf8", sym: "Bm" },
  "Tursiops truncatus":     { label: "Delfín Nariz Botella",latin: "T. truncatus",       color: "#34d399", sym: "Tt" },
  "Balaenoptera physalus":  { label: "Ballena de Aleta",    latin: "B. physalus",        color: "#60a5fa", sym: "Bp" },
  "Physeter macrocephalus": { label: "Cachalote",           latin: "P. macrocephalus",   color: "#a78bfa", sym: "Pm" },
  "Delphinus delphis":      { label: "Delfín Común",        latin: "D. delphis",         color: "#4ade80", sym: "Dd" },
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("es-MX", {
    month: "short", day: "numeric", year: "numeric",
  });
}

function fmtMmsi(mmsi: string): string {
  const n = mmsi.replace(".0", "");
  return n.length > 9 ? `${n.slice(0, 3)}···${n.slice(-3)}` : n;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ClassBar({ item, max }: { item: VesselClass; max: number }) {
  const meta = VESSEL_LABELS[item.vessel_type] ?? { label: item.vessel_type, color: "#6b7280" };
  const pct = max > 0 ? (item.count / max) * 100 : 0;
  return (
    <div className={styles.classRow}>
      <div className={styles.classLabel}>{meta.label}</div>
      <div className={styles.barTrack}>
        <div
          className={styles.barFill}
          style={{ width: `${pct}%`, background: meta.color }}
        />
      </div>
      <div className={styles.classCount}>{item.count.toLocaleString()}</div>
    </div>
  );
}

function VesselRow({ v, rank }: { v: TopVessel; rank: number }) {
  const meta = VESSEL_LABELS[v.vessel_type] ?? { label: v.vessel_type, color: "#6b7280" };
  return (
    <div className={styles.vesselRow}>
      <div className={styles.vesselRank}>{rank}</div>
      <div className={styles.vesselInfo}>
        <div className={styles.vesselMmsi}>MMSI {fmtMmsi(v.mmsi)}</div>
        <div className={styles.vesselSub}>{v.detections} detecciones</div>
      </div>
      <span className={styles.vesselBadge} style={{ borderColor: meta.color, color: meta.color }}>
        {meta.label}
      </span>
    </div>
  );
}

function SpeciesCard({ sp, yearData }: { sp: SpeciesRecord; yearData: YearRecord[] }) {
  const meta = SPECIES_LABELS[sp.species];
  const label = meta?.label ?? sp.species;
  const sym = meta?.sym ?? "??";
  const latin = meta?.latin ?? sp.species;
  const color = meta?.color ?? "#22d3ee";

  const years = yearData
    .filter((y) => y.species === sp.species)
    .sort((a, b) => a.year - b.year);
  const maxY = Math.max(...years.map((y) => y.count), 1);

  return (
    <div className={styles.speciesCard}>
      <div className={styles.speciesHeader}>
        <span
          className={styles.speciesEmoji}
          style={{
            color,
            border: `1px solid ${color}`,
            padding: "2px 4px",
            fontSize: 10,
            fontFamily: "IBM Plex Mono, monospace",
            fontWeight: 600,
            letterSpacing: 1,
            lineHeight: 1,
          }}
        >
          {sym}
        </span>
        <div>
          <div className={styles.speciesName}>{label}</div>
          <div className={styles.speciesLatin}>{latin}</div>
        </div>
        <div className={styles.speciesTotal} style={{ color }}>{sp.count.toLocaleString()}</div>
      </div>
      <div className={styles.speciesGroup}>{sp.taxa_group}</div>
      {years.length > 0 && (
        <div className={styles.yearBars}>
          {years.map((y) => (
            <div key={y.year} className={styles.yearRow}>
              <span className={styles.yearLabel}>{y.year}</span>
              <div className={styles.yearTrack}>
                <div
                  className={styles.yearFill}
                  style={{ width: `${(y.count / maxY) * 100}%`, background: color }}
                />
              </div>
              <span className={styles.yearCount}>{y.count.toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

interface IntelPanelProps {
  onClose?: () => void;
}

export default function IntelPanel({ onClose }: IntelPanelProps) {
  const [tab, setTab] = useState<"vessel" | "bay">("vessel");
  const [vesselData, setVesselData] = useState<VesselIntel | null>(null);
  const [bayData, setBayData] = useState<BayHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [v, b] = await Promise.all([
          supabase.rpc("get_vessel_intel"),
          supabase.rpc("get_bay_health"),
        ]);
        if (v.error) console.error("Error fetching get_vessel_intel:", v.error.message);
        if (b.error) console.error("Error fetching get_bay_health:", b.error.message);
        if (v.data) setVesselData(v.data as VesselIntel);
        if (b.data) setBayData(b.data as BayHealth);
      } catch (err) {
        console.error("Failed to load vessel intelligence from Supabase:", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const maxClass = vesselData
    ? Math.max(...(vesselData.by_class ?? []).map((c) => c.count), 1)
    : 1;

  const totalByClass = vesselData?.by_class?.reduce((s, c) => s + c.count, 0) ?? 0;

  return (
    <div className={`${styles.panel} ${expanded ? styles.expanded : styles.collapsed}`}>
      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className={styles.panelHeader}>
        <div className={styles.headerLeft}>
          <div className={styles.headerTitle}>Traffic Intelligence</div>
          {vesselData && (
            <div className={styles.headerSub}>
              {totalByClass.toLocaleString()} vessels · {fmtDate(vesselData.date_from)} – {fmtDate(vesselData.date_to)}
            </div>
          )}
        </div>
        <div className={styles.headerActions}>
          <button
            className={styles.toggleBtn}
            onClick={() => setExpanded((e) => !e)}
            aria-label="Colapsar"
          >
            {expanded ? "▲" : "▼"}
          </button>
          {onClose && (
            <button className={styles.closeBtn} onClick={onClose} aria-label="Cerrar">×</button>
          )}
        </div>
      </div>

      {/* ── Tabs ───────────────────────────────────────────────────── */}
      {expanded && (
        <>
          <div className={styles.tabs}>
            <button
              className={`${styles.tab} ${tab === "bay" ? styles.tabActive : ""}`}
              onClick={() => setTab("bay")}
            >
              Bay Health
            </button>
            <button
              className={`${styles.tab} ${tab === "vessel" ? styles.tabActive : ""}`}
              onClick={() => setTab("vessel")}
            >
              Vessel Intelligence
            </button>
          </div>

          <div className={styles.body}>
            {loading ? (
              <div className={styles.loading}>Cargando datos...</div>
            ) : tab === "vessel" ? (
              /* ── VESSEL INTEL ─────────────────────────────────── */
              <>
                {/* Summary stats */}
                {vesselData && (
                  <div className={styles.statsRow}>
                    <div className={styles.stat}>
                      <div className={styles.statNum} style={{ color: "#22d3ee" }}>
                        {(totalByClass).toLocaleString()}
                      </div>
                      <div className={styles.statLabel}>Total Vessels</div>
                    </div>
                    <div className={styles.stat}>
                      <div className={styles.statNum} style={{ color: "#22c55e" }}>
                        {(vesselData.by_class?.find(c => c.vessel_type === "fishing")?.count ?? 0)}
                      </div>
                      <div className={styles.statLabel}>Fishing</div>
                    </div>
                    <div className={styles.stat}>
                      <div className={styles.statNum} style={{ color: "#ef4444" }}>
                        {vesselData.dark_events ?? 0}
                      </div>
                      <div className={styles.statLabel}>Dark Events</div>
                    </div>
                  </div>
                )}

                {/* Activity by class */}
                <div className={styles.sectionTitle}>ACTIVITY BY VESSEL CLASS</div>
                <div className={styles.sectionSub}>
                  Based on {totalByClass.toLocaleString()} vessels · {fmtDate(vesselData?.date_from ?? null)} – {fmtDate(vesselData?.date_to ?? null)}
                </div>
                <div className={styles.classList}>
                  {(vesselData?.by_class ?? []).map((c) => (
                    <ClassBar key={c.vessel_type} item={c} max={maxClass} />
                  ))}
                </div>

                {/* Most active vessels */}
                <div className={styles.sectionTitle} style={{ marginTop: 16 }}>MOST ACTIVE VESSELS</div>
                <div className={styles.sectionSub}>By number of AIS detections in the study area</div>
                <div className={styles.vesselList}>
                  {(vesselData?.top_vessels ?? []).map((v, i) => (
                    <VesselRow key={v.mmsi} v={v} rank={i + 1} />
                  ))}
                </div>
              </>
            ) : (
              /* ── BAY HEALTH ────────────────────────────────────── */
              <>
                <div className={styles.sectionTitle}>BAY HEALTH INTELLIGENCE</div>
                <div className={styles.sectionSub}>
                  Species occurrence records from OBIS · {bayData?.total_records?.toLocaleString() ?? "—"} registros
                </div>
                <div className={styles.speciesList}>
                  {(bayData?.by_species ?? []).map((sp) => (
                    <SpeciesCard
                      key={sp.species}
                      sp={sp}
                      yearData={bayData?.by_year_species ?? []}
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
