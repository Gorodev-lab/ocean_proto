"use client";

/**
 * components/WorkflowGuide.tsx
 *
 * Infografía interactiva del flujo de trabajo de Ocean Proto.
 * Estilo: Esoteria — simbología científica, fórmulas, sintaxis de código.
 * Sin emojis. Sin border-radius. Sin sombras. IBM Plex Mono.
 */

import React, { useState } from "react";

// ── Slide data ────────────────────────────────────────────────

interface Slide {
  id: string;
  title: string;
  symbol: string;       // scientific/code symbol, NOT emoji
  formula: string;      // formula or code snippet
  description: string;
  details: string[];
  color: string;
  dataSource: string;
}

const SLIDES: Slide[] = [
  {
    id: "overview",
    title: "VISIÓN GENERAL",
    symbol: "Σ",
    formula: "data = AIS ∪ VMS ∪ S2_ML",
    description:
      "Ocean Proto integra 3 fuentes de datos complementarias para cuantificar la presión antropogénica sobre megafauna en el Golfo de California.",
    details: [
      "AIS := Automatic Identification System — tráfico marítimo global",
      "VMS := Vessel Monitoring System — flota CONAPESCA (pesqueros MX)",
      "S2_ML := Sentinel-2 + Machine Learning — buques sin señal (dark vessels)",
      "Cobertura: 46,292,000 ha | BCS + Sinaloa + ZEE",
    ],
    color: "#4a9eff",
    dataSource: "GFW.v3 | CONAPESCA.VMS | Copernicus.S2",
  },
  {
    id: "vessel-intel",
    title: "VESSEL INTELLIGENCE",
    symbol: "v(t)",
    formula: "classify(v) := f(speed, pattern, type)",
    description:
      "Clasificación de embarcaciones por velocidad y patrón de movimiento. Base: metodología IATTC + NOM-029.",
    details: [
      "palangre(v) := v.speed ∈ [0.1, 7.0] kn ∧ v.pattern = zigzag_largo",
      "arrastre(v) := v.speed ∈ [0.1, 5.0] kn ∧ v.pattern = zigzag_denso",
      "cerco(v)    := v.speed ∈ [0.1, 5.0] kn ∧ v.pattern = circular",
      "transito(v) := v.speed > 7.0 kn",
      "fondeo(v)   := v.speed < 0.1 kn",
    ],
    color: "#22d3ee",
    dataSource: "supabase.rpc('get_vessel_intel')",
  },
  {
    id: "bay-health",
    title: "SALUD DE LA BAHÍA",
    symbol: "H(β)",
    formula: "H = Σ species_i.count / total_records",
    description:
      "Índice de biodiversidad basado en registros de ocurrencia de cetáceos. Fuente: OBIS v3 (2023–2024).",
    details: [
      "Megaptera novaeangliae  n=9,934  (97.5%)",
      "Balaenoptera musculus   n=152    (1.5%)",
      "Tursiops truncatus      n=46     (0.5%)",
      "Balaenoptera physalus   n=26",
      "Physeter macrocephalus  n=18",
      "Delphinus delphis       n=8",
    ],
    color: "#00ff8c",
    dataSource: "supabase.rpc('get_bay_health')",
  },
  {
    id: "timeline",
    title: "LÍNEA DEL TIEMPO",
    symbol: "t(m)",
    formula: "series[m] = { vessels: Σv(m), megafauna: Σf(m), vedas: V(m) }",
    description:
      "Serie temporal mensual. Eje X: meses. Eje Y: detecciones. Superpone franjas de vedas y temporada de ballenas.",
    details: [
      "line(blue)  := vessel_count per month (AIS + VMS)",
      "line(green) := megafauna_count per month (OBIS)",
      "band(amber) := veda_camaron (Mar–Sep)",
      "band(red)   := veda_tiburon (May–Ago)",
      "band(cyan)  := whale_season (Dic–Abr, peak := Feb)",
    ],
    color: "#f59e0b",
    dataSource: "supabase.rpc('get_monthly_detections', { p_year })",
  },
  {
    id: "vedas",
    title: "VEDAS DE PESCA",
    symbol: "V(t)",
    formula: "is_active(sp, m) := m ∈ [veda.inicio, veda.fin] ∨ tipo = permanente",
    description:
      "Períodos de prohibición de pesca según normativa oficial mexicana. Definen ventanas de mayor vulnerabilidad.",
    details: [
      "V_atun_A    := [Jul.29, Oct.08]  NOM-235/IATTC   arte:cerco",
      "V_atun_B    := [Nov.09, Ene.19]  NOM-235/IATTC   arte:cerco   (75% flota)",
      "V_tiburon   := [May.01, Ago.01]  NOM-029-PESC-2006  arte:palangre",
      "V_camaron   := [Mar.03, Sep.29]  NOM-002-SAG/PESC-2013  arte:arrastre",
      "V_totoaba   := permanente  CONANP  (especie en peligro crítico)",
      "V_manta     := permanente  NOM-029-PESC-2006",
    ],
    color: "#ef4444",
    dataSource: "supabase.rpc('get_active_vedas', { p_mes })",
  },
  {
    id: "conflict",
    title: "ZONAS DE CONFLICTO",
    symbol: "IPA",
    formula: "IPA(h) = w₁·vessels(h) + w₂·megafauna(h) + w₃·fishing_hrs(h)",
    description:
      "Índice de Presión Antropogénica por celda hexagonal H3. Cuantifica la co-ocurrencia espacial vessel × megafauna.",
    details: [
      "IPA ≥ 80  →  CRÍTICO  (acción inmediata requerida)",
      "IPA ≥ 55  →  ALTO     (monitoreo intensificado)",
      "IPA ≥ 30  →  MEDIO    (vigilancia estándar)",
      "IPA < 30  →  BAJO     (sin intervención)",
      "score_cooccurrence := vessels ∩ megafauna en celda H3",
    ],
    color: "#a855f7",
    dataSource: "supabase.rpc('get_conflict_zones')",
  },
  {
    id: "workflow",
    title: "FLUJO DE TRABAJO",
    symbol: "λ",
    formula: "pipeline := observe >> contextualize >> identify >> evaluate >> act",
    description: "Secuencia de operaciones recomendada para analizar la zona de estudio.",
    details: [
      "01  OBSERVE     := load_map(layers=[vessels, megafauna, hotspots])",
      "02  CONTEXT     := read_timeline(year) → check_vedas(current_month)",
      "03  IDENTIFY    := query_vessel_intel() → classify_fleet(speed, type)",
      "04  EVALUATE    := check_bay_health() → compute_IPA(h3_cells)",
      "05  ACT         := if IPA ≥ 55 then flag_conflict_zone(h3_index)",
    ],
    color: "#22c55e",
    dataSource: "pipeline := Σ(all_sources)",
  },
];

// ── Component ─────────────────────────────────────────────────

interface WorkflowGuideProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function WorkflowGuide({ isOpen, onClose }: WorkflowGuideProps) {
  const [currentSlide, setCurrentSlide] = useState(0);

  if (!isOpen) return null;

  const slide = SLIDES[currentSlide];
  const isFirst = currentSlide === 0;
  const isLast = currentSlide === SLIDES.length - 1;

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0,0,0,0.88)",
        zIndex: 10000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "IBM Plex Mono, monospace",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "#0a0a0a",
          border: "1px solid #1a1a1a",
          width: "100%",
          maxWidth: 580,
          maxHeight: "90vh",
          overflowY: "auto",
          padding: 0,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Progress bar */}
        <div style={{ height: 1, background: "#111", position: "relative" }}>
          <div
            style={{
              height: 1,
              width: `${((currentSlide + 1) / SLIDES.length) * 100}%`,
              background: slide.color,
              transition: "width 0.3s ease",
            }}
          />
        </div>

        {/* Nav dots */}
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            gap: 4,
            padding: "14px 0 0 0",
          }}
        >
          {SLIDES.map((s, i) => (
            <button
              key={s.id}
              onClick={() => setCurrentSlide(i)}
              style={{
                width: i === currentSlide ? 24 : 8,
                height: 2,
                background: i === currentSlide ? slide.color : "#222",
                border: "none",
                cursor: "pointer",
                transition: "all 0.2s ease",
              }}
              aria-label={`Ir a ${s.title}`}
            />
          ))}
        </div>

        {/* Slide content */}
        <div style={{ padding: "20px 28px 24px" }}>
          {/* Symbol + Title */}
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: 12,
              marginBottom: 12,
            }}
          >
            <span
              style={{
                fontSize: 28,
                color: slide.color,
                fontWeight: 300,
                lineHeight: 1,
              }}
            >
              {slide.symbol}
            </span>
            <div>
              <div
                style={{
                  color: "#ccc",
                  fontSize: 11,
                  letterSpacing: 2,
                  fontWeight: 600,
                }}
              >
                {slide.title}
              </div>
              <div style={{ color: "#333", fontSize: 9 }}>
                {String(currentSlide).padStart(2, "0")}/{String(SLIDES.length - 1).padStart(2, "0")}
              </div>
            </div>
          </div>

          {/* Formula */}
          <div
            style={{
              background: "#111",
              border: "1px solid #1a1a1a",
              padding: "8px 14px",
              marginBottom: 14,
              fontSize: 11,
              color: slide.color,
              letterSpacing: 0.5,
              overflowX: "auto",
              whiteSpace: "nowrap",
            }}
          >
            <span style={{ color: "#444" }}>// </span>
            {slide.formula}
          </div>

          {/* Description */}
          <p
            style={{
              color: "#888",
              fontSize: 11,
              lineHeight: 1.7,
              marginBottom: 14,
            }}
          >
            {slide.description}
          </p>

          {/* Details as code block */}
          <div
            style={{
              borderLeft: `1px solid ${slide.color}`,
              paddingLeft: 14,
              marginBottom: 14,
            }}
          >
            {slide.details.map((d, i) => (
              <div
                key={i}
                style={{
                  color: "#777",
                  fontSize: 10,
                  lineHeight: 1.8,
                  fontFamily: "IBM Plex Mono, monospace",
                }}
              >
                <span style={{ color: "#333", marginRight: 8 }}>
                  {String(i).padStart(2, "0")}
                </span>
                {d}
              </div>
            ))}
          </div>

          {/* Data source */}
          <div
            style={{
              padding: "6px 0",
              fontSize: 9,
              color: "#333",
              borderTop: "1px solid #111",
              marginBottom: 18,
            }}
          >
            <span style={{ color: "#444" }}>source</span>{" "}
            <span style={{ color: "#555" }}>=</span>{" "}
            <span style={{ color: slide.color }}>{slide.dataSource}</span>
          </div>

          {/* Navigation */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <button
              onClick={() => setCurrentSlide((c) => Math.max(0, c - 1))}
              disabled={isFirst}
              style={{
                background: "transparent",
                border: `1px solid ${isFirst ? "#151515" : "#333"}`,
                color: isFirst ? "#222" : "#666",
                padding: "5px 14px",
                fontSize: 10,
                cursor: isFirst ? "default" : "pointer",
                fontFamily: "IBM Plex Mono, monospace",
                letterSpacing: 1,
              }}
            >
              &lt;&lt; PREV
            </button>

            {isLast ? (
              <button
                onClick={onClose}
                style={{
                  background: slide.color,
                  border: "none",
                  color: "#000",
                  padding: "5px 18px",
                  fontSize: 10,
                  cursor: "pointer",
                  fontWeight: 600,
                  fontFamily: "IBM Plex Mono, monospace",
                  letterSpacing: 1,
                }}
              >
                INIT &gt;&gt;
              </button>
            ) : (
              <button
                onClick={() =>
                  setCurrentSlide((c) => Math.min(SLIDES.length - 1, c + 1))
                }
                style={{
                  background: "transparent",
                  border: "1px solid #333",
                  color: "#666",
                  padding: "5px 14px",
                  fontSize: 10,
                  cursor: "pointer",
                  fontFamily: "IBM Plex Mono, monospace",
                  letterSpacing: 1,
                }}
              >
                NEXT &gt;&gt;
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
