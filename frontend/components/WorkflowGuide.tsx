"use client";

/**
 * components/WorkflowGuide.tsx
 *
 * Infografía interactiva del flujo de trabajo de Ocean Proto.
 * Muestra cómo interpretar y usar la información del dashboard.
 *
 * Se muestra como overlay al hacer clic en "?" o en la primera visita.
 * Estilo: Esoteria (IBM Plex Mono, sin bordes redondeados, sin sombras)
 */

import React, { useState } from "react";

// ── Slide data ────────────────────────────────────────────────

interface Slide {
  id: string;
  title: string;
  icon: string;
  description: string;
  details: string[];
  color: string;
  dataSource: string;
}

const SLIDES: Slide[] = [
  {
    id: "overview",
    title: "VISIÓN GENERAL",
    icon: "🌊",
    description:
      "Ocean Proto integra 3 fuentes de datos para vigilar la interacción entre flotas pesqueras y megafauna en BCS.",
    details: [
      "AIS — embarcaciones con transpondedor (tráfico global)",
      "VMS — flota pesquera nacional CONAPESCA",
      "Sentinel-2 ML — detecciones satelitales de buques sin señal (eventos oscuros)",
    ],
    color: "#4a9eff",
    dataSource: "Global Fishing Watch + CONAPESCA + Copernicus",
  },
  {
    id: "vessel-intel",
    title: "VESSEL INTELLIGENCE",
    icon: "🚢",
    description:
      "Clasifica embarcaciones por tipo y detecta patrones de actividad pesquera a partir de velocidad.",
    details: [
      "Palangre (tiburón): zigzag largo, 0.1–7 nudos",
      "Arrastre (camarón): zigzag denso, 0.1–5 nudos",
      "Cerco (atún): patrones circulares, 0.1–5 nudos",
      "Top vessels por número de detecciones AIS",
    ],
    color: "#22d3ee",
    dataSource: "Supabase → get_vessel_intel()",
  },
  {
    id: "bay-health",
    title: "SALUD DE LA BAHÍA",
    icon: "🐋",
    description:
      "Registros de megafauna por especie y año. Base: OBIS (Ocean Biodiversity Information System).",
    details: [
      "6 especies de cetáceos rastreadas en zona de estudio",
      "Jorobada dominante: 9,934 registros (2023–2024)",
      "Barras de tendencia por año para detectar cambios poblacionales",
      "Pico de avistamientos: Febrero (temporada Dic–Abr)",
    ],
    color: "#00ff8c",
    dataSource: "Supabase → get_bay_health()",
  },
  {
    id: "timeline",
    title: "LÍNEA DEL TIEMPO",
    icon: "📊",
    description:
      "Serie temporal mensual: cruce de detecciones de vessels y megafauna con periodos de veda.",
    details: [
      "Línea azul: embarcaciones AIS/VMS por mes",
      "Línea verde: avistamientos de megafauna OBIS",
      "Franjas de color: períodos de veda por especie objetivo",
      "Barra cyan: época de ballenas (Dic–Abr)",
    ],
    color: "#f59e0b",
    dataSource: "Supabase → get_monthly_detections(year)",
  },
  {
    id: "vedas",
    title: "VEDAS DE PESCA",
    icon: "🚫",
    description:
      "Períodos oficiales donde se prohíbe la pesca de especies específicas según normativa mexicana.",
    details: [
      "🐟 Atún: Veda A (Jul–Oct) o B (Nov–Ene) — NOM-235/IATTC",
      "🦈 Tiburón: May–Ago — NOM-029-PESC-2006",
      "🦐 Camarón: Mar–Sep — NOM-002-SAG/PESC-2013",
      "⛔ Totoaba + Manta Raya: permanente",
    ],
    color: "#ef4444",
    dataSource: "Supabase → get_active_vedas(mes)",
  },
  {
    id: "conflict",
    title: "ZONAS DE CONFLICTO",
    icon: "⚠️",
    description:
      "Celdas hexagonales H3 donde existe co-ocurrencia confirmada de embarcaciones y megafauna.",
    details: [
      "IPA (Índice de Presión Antropogénica): 0–100",
      "CRÍTICO = IPA ≥ 80 (vessel + megafauna + fishing hours)",
      "ALTO = IPA ≥ 55 (co-ocurrencia significativa)",
      "Click en celda → análisis Gemini con contexto TONL",
    ],
    color: "#a855f7",
    dataSource: "Supabase → get_conflict_zones()",
  },
  {
    id: "workflow",
    title: "FLUJO DE TRABAJO",
    icon: "🔄",
    description: "Secuencia recomendada para analizar una situación en la zona de estudio.",
    details: [
      "1. OBSERVAR — Revisar mapa con capas activas (vessels + megafauna + hotspots)",
      "2. CONTEXTUALIZAR — Ver Timeline para entender la temporalidad (¿estamos en veda?)",
      "3. IDENTIFICAR — Usar Vessel Intel para clasificar embarcaciones activas",
      "4. EVALUAR — Revisar Bay Health para estado de biodiversidad",
      "5. ACTUAR — Zonas de conflicto IPA ≥ 55 requieren atención prioritaria",
    ],
    color: "#22c55e",
    dataSource: "Integración de todas las fuentes",
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
        background: "rgba(0,0,0,0.85)",
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
          border: "1px solid #222",
          width: "100%",
          maxWidth: 560,
          maxHeight: "90vh",
          overflowY: "auto",
          padding: 0,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Progress bar */}
        <div
          style={{
            height: 2,
            background: "#111",
            position: "relative",
          }}
        >
          <div
            style={{
              height: 2,
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
            gap: 6,
            padding: "12px 0 0 0",
          }}
        >
          {SLIDES.map((s, i) => (
            <button
              key={s.id}
              onClick={() => setCurrentSlide(i)}
              style={{
                width: i === currentSlide ? 20 : 8,
                height: 8,
                background: i === currentSlide ? slide.color : "#333",
                border: "none",
                cursor: "pointer",
                transition: "all 0.2s ease",
              }}
              aria-label={`Ir a ${s.title}`}
            />
          ))}
        </div>

        {/* Slide content */}
        <div style={{ padding: "24px 28px" }}>
          {/* Icon + Title */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              marginBottom: 16,
            }}
          >
            <span style={{ fontSize: 28 }}>{slide.icon}</span>
            <div>
              <div
                style={{
                  color: slide.color,
                  fontSize: 11,
                  letterSpacing: 2,
                  fontWeight: 600,
                }}
              >
                {slide.title}
              </div>
              <div style={{ color: "#555", fontSize: 9 }}>
                {currentSlide + 1} / {SLIDES.length}
              </div>
            </div>
          </div>

          {/* Description */}
          <p
            style={{
              color: "#ccc",
              fontSize: 12,
              lineHeight: 1.6,
              marginBottom: 16,
            }}
          >
            {slide.description}
          </p>

          {/* Details */}
          <div
            style={{
              borderLeft: `2px solid ${slide.color}`,
              paddingLeft: 12,
              marginBottom: 16,
            }}
          >
            {slide.details.map((d, i) => (
              <div
                key={i}
                style={{
                  color: "#999",
                  fontSize: 11,
                  lineHeight: 1.7,
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 8,
                }}
              >
                <span style={{ color: slide.color, flexShrink: 0 }}>▸</span>
                <span>{d}</span>
              </div>
            ))}
          </div>

          {/* Data source */}
          <div
            style={{
              background: "#111",
              padding: "8px 12px",
              fontSize: 9,
              color: "#555",
              marginBottom: 20,
            }}
          >
            FUENTE: {slide.dataSource}
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
                border: `1px solid ${isFirst ? "#222" : "#444"}`,
                color: isFirst ? "#333" : "#999",
                padding: "6px 16px",
                fontSize: 10,
                cursor: isFirst ? "default" : "pointer",
                fontFamily: "IBM Plex Mono, monospace",
              }}
            >
              ◀ ANTERIOR
            </button>

            {isLast ? (
              <button
                onClick={onClose}
                style={{
                  background: slide.color,
                  border: "none",
                  color: "#000",
                  padding: "6px 20px",
                  fontSize: 10,
                  cursor: "pointer",
                  fontWeight: 600,
                  fontFamily: "IBM Plex Mono, monospace",
                }}
              >
                COMENZAR ▸
              </button>
            ) : (
              <button
                onClick={() =>
                  setCurrentSlide((c) => Math.min(SLIDES.length - 1, c + 1))
                }
                style={{
                  background: "transparent",
                  border: `1px solid #444`,
                  color: "#999",
                  padding: "6px 16px",
                  fontSize: 10,
                  cursor: "pointer",
                  fontFamily: "IBM Plex Mono, monospace",
                }}
              >
                SIGUIENTE ▶
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
