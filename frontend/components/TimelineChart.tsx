"use client";

/**
 * components/TimelineChart.tsx
 *
 * Gráfico de línea del tiempo: detecciones mensuales de embarcaciones
 * y megafauna, con franjas de vedas y época de ballenas.
 *
 * Estilo: Esoteria (IBM Plex Mono, sin border-radius, sin sombras, #0a0a0a)
 */

import React, { useEffect, useRef, useState } from "react";
import * as d3 from "d3";

interface MonthlyData {
  month: number;
  label: string;
  vessel_count: number;
  megafauna_count: number;
  dominant_species: string | null;
  is_whale_season: boolean;
  vedas: {
    atun_a: boolean;
    atun_b: boolean;
    tiburon: boolean;
    camaron: boolean;
    any: boolean;
  };
}

interface TimelineResponse {
  year: number;
  monthly: MonthlyData[];
  summary: {
    total_vessel_detections: number;
    total_megafauna_sightings: number;
    peak_vessel_month: string;
    peak_megafauna_month: string;
    whale_season_months: string[];
  };
}

interface VedaItem {
  nombre: string;
  especie: string;
  periodo: string | null;
  norma: string | null;
  icon: string;
}

interface VedasResponse {
  currentMonth: number;
  active: VedaItem[];
  upcoming: VedaItem[];
}

const YEARS = [2023, 2024];
const MARGIN = { top: 24, right: 24, bottom: 40, left: 52 };

export default function TimelineChart() {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [year, setYear] = useState(2024);
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [vedas, setVedas] = useState<VedasResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeLayer, setActiveLayer] = useState<"vessels" | "megafauna" | "both">("both");

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`/api/timeline?year=${year}`).then((r) => r.json()),
      fetch("/api/vedas").then((r) => r.json()),
    ])
      .then(([t, v]) => {
        setData(t);
        setVedas(v);
      })
      .finally(() => setLoading(false));
  }, [year]);

  useEffect(() => {
    if (!data || !svgRef.current || !containerRef.current) return;

    const container = containerRef.current;
    const W = container.clientWidth;
    const H = 220;
    const w = W - MARGIN.left - MARGIN.right;
    const h = H - MARGIN.top - MARGIN.bottom;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("width", W).attr("height", H);

    const g = svg
      .append("g")
      .attr("transform", `translate(${MARGIN.left},${MARGIN.top})`);

    const monthly = data.monthly;
    const x = d3
      .scaleBand()
      .domain(monthly.map((d) => d.label))
      .range([0, w])
      .padding(0.1);

    const maxVal = d3.max(monthly, (d) =>
      Math.max(d.vessel_count, d.megafauna_count)
    ) ?? 100;
    const y = d3.scaleLinear().domain([0, maxVal * 1.15]).range([h, 0]);

    // ── Veda bands ─────────────────────────────────────────────
    const vedaColors: Record<string, string> = {
      camaron: "rgba(255,180,0,0.12)",
      tiburon: "rgba(255,80,80,0.12)",
      atun_a:  "rgba(255,120,0,0.12)",
      atun_b:  "rgba(255,60,120,0.12)",
    };

    const vedaKeys = ["camaron", "tiburon", "atun_a", "atun_b"] as const;
    vedaKeys.forEach((vk) => {
      monthly.forEach((d) => {
        const active = vk === "camaron" ? d.vedas.camaron
          : vk === "tiburon" ? d.vedas.tiburon
          : vk === "atun_a" ? d.vedas.atun_a
          : d.vedas.atun_b;
        if (!active) return;
        const bx = x(d.label);
        if (bx === undefined) return;
        g.append("rect")
          .attr("x", bx)
          .attr("y", 0)
          .attr("width", x.bandwidth())
          .attr("height", h)
          .attr("fill", vedaColors[vk])
          .attr("pointer-events", "none");
      });
    });

    // ── Whale season band ──────────────────────────────────────
    monthly.forEach((d) => {
      if (!d.is_whale_season) return;
      const bx = x(d.label);
      if (bx === undefined) return;
      g.append("rect")
        .attr("x", bx)
        .attr("y", 0)
        .attr("width", x.bandwidth())
        .attr("height", 4)
        .attr("fill", "#00d4ff")
        .attr("opacity", 0.7);
    });

    // ── Area fill for megafauna ────────────────────────────────
    if (activeLayer !== "vessels") {
      const areaGen = d3
        .area<MonthlyData>()
        .x((d) => (x(d.label) ?? 0) + x.bandwidth() / 2)
        .y0(h)
        .y1((d) => y(d.megafauna_count))
        .curve(d3.curveMonotoneX);

      g.append("path")
        .datum(monthly)
        .attr("fill", "rgba(0,255,140,0.07)")
        .attr("d", areaGen);
    }

    // ── Lines ──────────────────────────────────────────────────
    const lineGen = (key: "vessel_count" | "megafauna_count") =>
      d3
        .line<MonthlyData>()
        .x((d) => (x(d.label) ?? 0) + x.bandwidth() / 2)
        .y((d) => y(d[key]))
        .curve(d3.curveMonotoneX);

    if (activeLayer !== "megafauna") {
      g.append("path")
        .datum(monthly)
        .attr("fill", "none")
        .attr("stroke", "#4a9eff")
        .attr("stroke-width", 1.5)
        .attr("d", lineGen("vessel_count"));
    }

    if (activeLayer !== "vessels") {
      g.append("path")
        .datum(monthly)
        .attr("fill", "none")
        .attr("stroke", "#00ff8c")
        .attr("stroke-width", 1.5)
        .attr("d", lineGen("megafauna_count"));
    }

    // ── Dots ───────────────────────────────────────────────────
    monthly.forEach((d) => {
      const cx = (x(d.label) ?? 0) + x.bandwidth() / 2;
      if (activeLayer !== "megafauna" && d.vessel_count > 0) {
        g.append("circle")
          .attr("cx", cx)
          .attr("cy", y(d.vessel_count))
          .attr("r", 2.5)
          .attr("fill", "#4a9eff");
      }
      if (activeLayer !== "vessels" && d.megafauna_count > 0) {
        g.append("circle")
          .attr("cx", cx)
          .attr("cy", y(d.megafauna_count))
          .attr("r", 2.5)
          .attr("fill", "#00ff8c");
      }
    });

    // ── Axes ───────────────────────────────────────────────────
    g.append("g")
      .attr("transform", `translate(0,${h})`)
      .call(d3.axisBottom(x).tickSize(0))
      .call((axis) => {
        axis.select(".domain").attr("stroke", "#333");
        axis.selectAll("text")
          .attr("fill", "#666")
          .style("font-family", "IBM Plex Mono, monospace")
          .style("font-size", "10px");
      });

    g.append("g")
      .call(
        d3
          .axisLeft(y)
          .ticks(4)
          .tickFormat((v) => (Number(v) >= 1000 ? `${Number(v) / 1000}k` : String(v)))
      )
      .call((axis) => {
        axis.select(".domain").remove();
        axis.selectAll(".tick line").attr("stroke", "#222").attr("x2", w);
        axis.selectAll("text")
          .attr("fill", "#555")
          .style("font-family", "IBM Plex Mono, monospace")
          .style("font-size", "10px");
      });
  }, [data, activeLayer]);

  return (
    <div style={{ fontFamily: "IBM Plex Mono, monospace" }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
        }}
      >
        <div>
          <span style={{ color: "#666", fontSize: 10, letterSpacing: 2 }}>
            &gt; LÍNEA DEL TIEMPO
          </span>
          <div style={{ color: "#ccc", fontSize: 11, marginTop: 2 }}>
            Detecciones mensuales · AIS + VMS + OBIS
          </div>
        </div>

        {/* Year selector */}
        <div style={{ display: "flex", gap: 4 }}>
          {YEARS.map((y) => (
            <button
              key={y}
              onClick={() => setYear(y)}
              style={{
                background: year === y ? "#4a9eff" : "transparent",
                border: `1px solid ${year === y ? "#4a9eff" : "#333"}`,
                color: year === y ? "#000" : "#666",
                padding: "2px 8px",
                fontSize: 10,
                cursor: "pointer",
                fontFamily: "IBM Plex Mono, monospace",
              }}
            >
              {y}
            </button>
          ))}
        </div>
      </div>

      {/* Layer toggles */}
      <div style={{ display: "flex", gap: 12, marginBottom: 8 }}>
        {(["both", "vessels", "megafauna"] as const).map((l) => (
          <button
            key={l}
            onClick={() => setActiveLayer(l)}
            style={{
              background: "transparent",
              border: "none",
              color: activeLayer === l ? "#fff" : "#555",
              fontSize: 10,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 4,
              fontFamily: "IBM Plex Mono, monospace",
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                background:
                  l === "vessels" ? "#4a9eff" : l === "megafauna" ? "#00ff8c" : "#888",
                display: "inline-block",
              }}
            />
            {l === "both" ? "AMBOS" : l === "vessels" ? "EMBARCACIONES" : "MEGAFAUNA"}
          </button>
        ))}
      </div>

      {/* Chart */}
      <div ref={containerRef} style={{ width: "100%" }}>
        {loading ? (
          <div
            style={{
              height: 220,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#333",
              fontSize: 10,
            }}
          >
            CARGANDO...
          </div>
        ) : (
          <svg ref={svgRef} style={{ width: "100%", display: "block" }} />
        )}
      </div>

      {/* Legend */}
      <div
        style={{
          display: "flex",
          gap: 16,
          marginTop: 8,
          flexWrap: "wrap",
          fontSize: 9,
          color: "#555",
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 20, height: 2, background: "#4a9eff", display: "inline-block" }} />
          Embarcaciones AIS/VMS
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 20, height: 2, background: "#00ff8c", display: "inline-block" }} />
          Megafauna OBIS
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 12, height: 12, background: "rgba(255,180,0,0.3)", display: "inline-block" }} />
          Veda camarón
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 12, height: 12, background: "rgba(255,80,80,0.3)", display: "inline-block" }} />
          Veda tiburón
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 20, height: 4, background: "#00d4ff", display: "inline-block" }} />
          Época ballenas
        </span>
      </div>

      {/* Active vedas panel */}
      {vedas && vedas.active.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ color: "#666", fontSize: 9, letterSpacing: 2, marginBottom: 6 }}>
            &gt; VEDAS ACTIVAS ESTE MES
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {vedas.active.map((v) => (
              <div
                key={v.nombre}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  borderLeft: "2px solid #ff4444",
                  paddingLeft: 8,
                  paddingTop: 2,
                  paddingBottom: 2,
                }}
              >
                <span style={{ color: "#ccc", fontSize: 10 }}>
                  {v.icon} {v.nombre}
                </span>
                <span style={{ color: "#666", fontSize: 9 }}>
                  {v.periodo ?? "Permanente"} · {v.norma}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Summary stats */}
      {data?.summary && !loading && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 8,
            marginTop: 12,
            paddingTop: 12,
            borderTop: "1px solid #1a1a1a",
          }}
        >
          {[
            { label: "PICO EMBARCACIONES", value: data.summary.peak_vessel_month },
            { label: "PICO MEGAFAUNA", value: data.summary.peak_megafauna_month },
            {
              label: "TOTAL DETECCIONES",
              value: data.summary.total_vessel_detections.toLocaleString(),
            },
            {
              label: "TOTAL AVISTAMIENTOS",
              value: data.summary.total_megafauna_sightings.toLocaleString(),
            },
          ].map((s) => (
            <div key={s.label}>
              <div style={{ color: "#555", fontSize: 8, letterSpacing: 1 }}>{s.label}</div>
              <div style={{ color: "#fff", fontSize: 12, marginTop: 2 }}>{s.value ?? "—"}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
