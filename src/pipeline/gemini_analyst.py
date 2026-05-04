"""
ocean_proto / src / pipeline / gemini_analyst.py
=================================================
Gemini AI Risk Analyst — Harness + Memory + Prompt Engineering

Arquitectura de 3 capas:
  1. HARNESS   — Wrapper sobre google-generativeai con retry, timeout y
                 fallback estructurado. Expone una interfaz limpia al resto
                 del pipeline.

  2. MEMORY    — Contexto persistente construido desde los artefactos del
                 pipeline: hotspots H3 (IPA), gap events, estacionalidad,
                 y conocimiento del dominio oceanográfico/GFW.

  3. PROMPT    — Plantillas especializadas para distintas tareas:
                   - analyze_hotspot()   → narrativa de riesgo por celda
                   - synthesize_region() → resumen ejecutivo del área
                   - suggest_action()    → recomendaciones de mitigación
                   - explain_ipa()       → explicación del score para papers

Estrategia de integración (alta probabilidad, baja dificultad):
  - No modifica el pipeline de datos — es una capa READ-ONLY encima del output
  - Usa los GeoJSONs y CSVs ya generados como fuente de verdad
  - Agrega valor narrativo e interpretación científica sin riesgo de regresión
"""

import os
import json
import logging
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── SDK de Gemini (nuevo: google-genai) ──────────────────────────────────────
try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("[Gemini] google-genai no instalado. Ejecuta: pip install google-genai")


# ── Configuración del modelo ──────────────────────────────────────────────────
GEMINI_MODEL   = "gemini-2.5-flash"   # Disponible en Tier Free (2026)
MAX_RETRIES    = 3
RETRY_DELAY    = 2.0   # segundos entre reintentos
MAX_TOKENS     = 2048
TEMPERATURE    = 0.3   # Baja temperatura → respuestas más deterministas / científicas


# ── CAPA 1: HARNESS ──────────────────────────────────────────────────────────

def _get_client():
    """
    Inicializa y retorna el cliente Gemini (google-genai SDK moderno).
    """
    if not GEMINI_AVAILABLE:
        return None

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("[Gemini] GEMINI_API_KEY no configurada en .env")
        return None

    return genai.Client(api_key=api_key)


def _call_gemini(prompt: str, context: str = "") -> str:
    """
    Harness central: llama a Gemini con reintentos y fallback.
    Usa google-genai SDK moderno (client.models.generate_content).
    """
    client = _get_client()
    if client is None:
        return _fallback_response(prompt)

    full_prompt = f"{context}\n\n{prompt}" if context else prompt

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"[Gemini] Llamada al modelo ({attempt}/{MAX_RETRIES})...")
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=full_prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=TEMPERATURE,
                    max_output_tokens=MAX_TOKENS,
                ),
            )
            text = response.text.strip()
            logger.info(f"[Gemini] Respuesta recibida ({len(text)} chars).")
            return text
        except Exception as e:
            logger.warning(f"[Gemini] Intento {attempt} fallido: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

    return _fallback_response(prompt)


def _fallback_response(prompt: str) -> str:
    """Respuesta de fallback cuando Gemini no está disponible."""
    return json.dumps({
        "status":  "unavailable",
        "message": "Gemini API no disponible en este momento.",
        "prompt":  prompt[:100] + "...",
    })


# ── CAPA 2: MEMORY ENGINEERING ───────────────────────────────────────────────

def build_pipeline_memory() -> str:
    """
    Construye el contexto de memoria del pipeline para Gemini.

    Lee los artefactos generados por el pipeline GFW y los condensa
    en un bloque de contexto estructurado que se inyecta en cada prompt.

    Incluye:
      - Resumen de hotspots IPA (top 5 celdas de riesgo)
      - Conteos de gap events, encounters, loitering
      - Estacionalidad actual
      - Metadatos del área de estudio
    """
    memory_parts = []

    # --- Metadatos del área de estudio ---
    memory_parts.append(
        "SYSTEM CONTEXT — Ocean Risk Analyzer (GFW-Only Pipeline)\n"
        "Area of study: Gulf of California / Baja California Sur, Mexico\n"
        "Bounding box: 22°N–32°N, 118°W–105°W\n"
        "Analysis period: 2023-2024\n"
        "Spatial index: H3 hexagonal grid (resolution 5, ~50km diameter)\n"
        "Risk metric: Índice de Presión Antrópica (IPA) — 7-dimensional GFW-only score\n"
    )

    # --- Top hotspots desde el GeoJSON generado ---
    hotspot_path = "data/risk_hotspots.geojson"
    if os.path.exists(hotspot_path):
        try:
            with open(hotspot_path) as f:
                gj = json.load(f)
            features = gj.get("features", [])
            # Ordenar por IPA
            features_sorted = sorted(
                features,
                key=lambda x: x.get("properties", {}).get("ipa_100", 0),
                reverse=True
            )[:5]

            if features_sorted:
                memory_parts.append("\nTOP-5 PRESSURE HOTSPOTS (IPA Score):")
                for i, feat in enumerate(features_sorted, 1):
                    props = feat.get("properties", {})
                    h3    = props.get("h3_index", "N/A")
                    ipa   = props.get("ipa_100", 0)
                    level = props.get("ipa_level", "N/A")
                    vessels = props.get("vessel_count", 0)
                    gaps    = props.get("gap_count", 0)
                    memory_parts.append(
                        f"  {i}. Cell {h3}: IPA={ipa:.1f}/100 [{level}] "
                        f"| vessels={vessels} | ais_gaps={gaps}"
                    )
        except Exception as e:
            logger.warning(f"[Memory] No se pudo leer hotspots: {e}")
    else:
        memory_parts.append("\n[NOTE: No hotspot data available yet. Run /api/refresh first.]")

    # --- Gap events ---
    gap_path = "data/gfw_gap_events_cache.json"
    if os.path.exists(gap_path):
        try:
            with open(gap_path) as f:
                gaps = json.load(f)
            total_gaps = len(gaps)
            long_gaps  = sum(1 for g in gaps if g.get("gap_hours", 0) > 24)
            memory_parts.append(
                f"\nGAP EVENTS SUMMARY: {total_gaps} total | {long_gaps} lasting >24h"
            )
        except Exception:
            pass

    # --- Encounters ---
    enc_path = "data/gfw_encounters_cache.json"
    if os.path.exists(enc_path):
        try:
            with open(enc_path) as f:
                enc = json.load(f)
            memory_parts.append(f"ENCOUNTER EVENTS: {len(enc)} potential at-sea transshipments")
        except Exception:
            pass

    # --- Loitering ---
    loi_path = "data/gfw_loitering_cache.json"
    if os.path.exists(loi_path):
        try:
            with open(loi_path) as f:
                loi = json.load(f)
            memory_parts.append(f"LOITERING EVENTS: {len(loi)} detected")
        except Exception:
            pass

    # --- Estacionalidad ---
    current_month = datetime.now().month
    try:
        from src.pipeline.seasonal import compute_seasonal_summary
        season = compute_seasonal_summary(current_month)
        memory_parts.append(
            f"\nCURRENT SEASON (month={current_month}): "
            f"{season['season_label']} | pressure_modifier={season['pressure_modifier']} "
            f"| level={season['pressure_level']} "
            f"| is_veda={season['is_veda']}"
        )
    except Exception:
        pass

    return "\n".join(memory_parts)


# ── CAPA 3: PROMPT ENGINEERING ───────────────────────────────────────────────

def analyze_hotspot(
    h3_index:     str,
    ipa_score:    float,
    vessel_count: int,
    gap_count:    int   = 0,
    enc_count:    int   = 0,
    loi_count:    int   = 0,
    month:        int   = None,
) -> dict:
    """
    Genera un análisis narrativo en lenguaje natural para una celda H3.

    Tarea de prompt: explicar el score IPA en lenguaje de ciencia de datos
    con contexto oceanográfico y recomendaciones.
    """
    month = month or datetime.now().month
    context = build_pipeline_memory()

    prompt = f"""You are an expert marine biologist and data scientist analyzing
vessel-megafauna collision risk in the Gulf of California, Mexico.

Analyze the following H3 hexagonal cell data and provide a structured
scientific interpretation in SPANISH:

CELL DATA:
- H3 Index: {h3_index}
- IPA Score: {ipa_score:.1f}/100
- Vessel Detections (SAR/AIS): {vessel_count}
- AIS Gap Events (transponder off): {gap_count}
- Vessel Encounter Events: {enc_count}
- Loitering Events: {loi_count}
- Current Month: {month}

Provide your analysis in the following JSON structure ONLY (no markdown):
{{
  "risk_summary": "2-sentence summary of the risk level and main drivers",
  "main_drivers": ["list", "of", "key", "risk", "factors"],
  "species_concern": "which megafauna species are most at risk here and why",
  "recommended_actions": ["specific", "conservation", "recommendations"],
  "confidence": "HIGH | MEDIUM | LOW — confidence in this assessment",
  "data_quality_notes": "any limitations of GFW-only analysis for this cell"
}}"""

    raw = _call_gemini(prompt, context=context)

    # Intentar parsear como JSON, fallback a texto
    try:
        # Limpiar posibles bloques ```json ... ```
        cleaned = raw.strip().lstrip("```json").rstrip("```").strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "risk_summary":         raw[:300],
            "main_drivers":         ["Análisis narrativo"],
            "species_concern":      "Ver análisis completo",
            "recommended_actions":  [],
            "confidence":           "MEDIUM",
            "data_quality_notes":   "Respuesta en formato texto",
            "_raw":                 raw,
        }


def synthesize_region(top_n: int = 5) -> dict:
    """
    Genera un resumen ejecutivo del área de estudio completa.
    Ideal para el abstract de un paper o reporte de grant.
    """
    context = build_pipeline_memory()
    current_month = datetime.now().month

    prompt = f"""You are a senior oceanographic data scientist preparing a
scientific summary for the 2026 Open Ocean Research Grant application.

Based on the GFW-Only pipeline data for the Gulf of California (BCS, Mexico),
generate an executive summary in SPANISH in the following JSON format ONLY:

{{
  "executive_summary": "3-4 sentences for grant executive summary",
  "key_findings": ["finding 1", "finding 2", "finding 3"],
  "hotspot_count_critical": <estimated number of critical cells>,
  "primary_threat": "main anthropogenic threat identified",
  "data_coverage": "assessment of GFW-only data quality for this region",
  "grant_alignment": "how this data supports Open Ocean Research Grant themes",
  "next_steps": ["immediate", "research", "recommendations"]
}}

Current analysis month: {current_month}
Top {top_n} hotspots analyzed from the IPA index."""

    raw = _call_gemini(prompt, context=context)
    try:
        cleaned = raw.strip().lstrip("```json").rstrip("```").strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"executive_summary": raw, "_raw": raw}


def explain_ipa_for_paper() -> str:
    """
    Genera una explicación metodológica del IPA para sección de métodos
    de un paper científico.
    """
    context = build_pipeline_memory()

    prompt = """Write a concise METHODS section paragraph (150-200 words, in English)
describing the Anthropic Pressure Index (IPA) methodology for a peer-reviewed
marine conservation journal. Use formal scientific language.

The IPA uses exclusively Global Fishing Watch datasets:
- Traffic density (SAR + AIS presence, weight=0.25)
- Acoustic impact model (weight=0.20)
- Fishing effort proxy for habitat quality (weight=0.15)
- Behavioral anomaly score: gaps + encounters + loitering (weight=0.15)
- O&G infrastructure pressure (weight=0.10)
- Navigation corridor intensity (weight=0.10)
- Vessel identity risk (weight=0.05)

All scores normalized to [0,1] via min-max scaling, spatially aggregated
to H3 hexagonal cells (resolution 5, ~50km), with fishing seasonality
temporal modifier applied."""

    return _call_gemini(prompt, context=context)


def quick_status() -> dict:
    """
    Test rápido de conectividad con Gemini API.
    Retorna estado y latencia.
    """
    t0 = time.time()
    response = _call_gemini(
        "Respond with exactly: {\"status\": \"ok\", \"model\": \"gemini-1.5-flash\"}",
        context="",
    )
    latency_ms = int((time.time() - t0) * 1000)

    try:
        cleaned = response.strip().lstrip("```json").rstrip("```").strip()
        data = json.loads(cleaned)
        data["latency_ms"] = latency_ms
        data["available"]  = True
        return data
    except Exception:
        return {
            "status":     "error",
            "available":  False,
            "latency_ms": latency_ms,
            "raw":        response[:100],
        }
