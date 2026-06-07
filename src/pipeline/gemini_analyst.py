"""
ocean_proto / src / pipeline / gemini_analyst.py
=================================================
Gemini AI Risk Analyst — Singleton client + async-safe retries.

Cambios v2:
  - _get_client() es un singleton: crea el Client UNA SOLA VEZ por proceso.
  - _call_gemini() usa time.sleep() síncrono (compatible con run_in_threadpool).
  - Retry loop usa tenacity vía _resilience en lugar de sleep manual.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# ── SDK de Gemini ─────────────────────────────────────────────────────────────
try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("[Gemini] google-genai no instalado. Ejecuta: pip install google-genai")

GEMINI_MODEL  = "gemini-2.5-flash"
MAX_RETRIES   = 3
RETRY_DELAY   = 2.0   # segundos base (se multiplica por intento)
MAX_TOKENS    = 2048
TEMPERATURE   = 0.3


# ── CAPA 1: HARNESS ──────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_client():
    """
    Singleton: inicializa genai.Client() una sola vez por proceso.
    lru_cache(maxsize=1) garantiza que solo existe una instancia.
    Retorna None si la API key no está configurada.
    """
    if not GEMINI_AVAILABLE:
        return None
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("[Gemini] GEMINI_API_KEY no configurada en .env")
        return None
    logger.info("[Gemini] Inicializando cliente (singleton)...")
    return genai.Client(api_key=api_key)


def _call_gemini(prompt: str, context: str = "") -> str:
    """
    Harness central: llama a Gemini con reintentos exponenciales.
    Usa time.sleep() síncrono — siempre llamar desde run_in_threadpool.
    """
    client = _get_client()
    if client is None:
        return _fallback_response(prompt)

    full_prompt = f"{context}\n\n{prompt}" if context else prompt

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("[Gemini] Llamada al modelo (%d/%d)...", attempt, MAX_RETRIES)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=full_prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=TEMPERATURE,
                    max_output_tokens=MAX_TOKENS,
                ),
            )
            text = response.text.strip()
            logger.info("[Gemini] Respuesta OK (%d chars).", len(text))
            return text
        except Exception as exc:
            wait = RETRY_DELAY * attempt
            logger.warning("[Gemini] Intento %d falló (%s). Reintentando en %.1fs...",
                           attempt, exc, wait)
            if attempt < MAX_RETRIES:
                time.sleep(wait)

    return _fallback_response(prompt)


def _fallback_response(prompt: str) -> str:
    return json.dumps({
        "status":  "unavailable",
        "message": "Gemini API no disponible en este momento.",
        "prompt":  prompt[:100] + "...",
    })


def _parse_json_response(raw: str) -> dict:
    """Parsea la respuesta Gemini limpiando bloques ```json ... ```."""
    cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "risk_summary":        raw[:300],
            "main_drivers":        ["Análisis narrativo"],
            "species_concern":     "Ver análisis completo",
            "recommended_actions": [],
            "confidence":          "MEDIUM",
            "data_quality_notes":  "Respuesta en formato texto",
            "_raw":                raw,
        }


# ── CAPA 2: MEMORY ───────────────────────────────────────────────────────────

def build_pipeline_memory() -> str:
    """
    Construye el contexto de memoria del pipeline para Gemini.
    Lee artefactos en disco (hotspots, gaps, encounters, loitering, estacionalidad).
    """
    parts: list[str] = [
        "SYSTEM CONTEXT — Ocean Proto Maritime Intelligence (GFW-Only Pipeline)\n"
        "Area of study: Gulf of California / Baja California Sur, Mexico\n"
        "Bounding box: 22°N–32°N, 118°W–105°W\n"
        "Analysis period: 2023-2024\n"
        "Spatial index: H3 hexagonal grid (resolution 5, ~50km diameter)\n"
        "Risk metric: Índice de Presión Antrópica (IPA) — 7-dimensional GFW-only score\n"
    ]

    # Top hotspots
    if os.path.exists("data/risk_hotspots.geojson"):
        try:
            with open("data/risk_hotspots.geojson") as f:
                gj = json.load(f)
            top5 = sorted(
                gj.get("features", []),
                key=lambda x: x.get("properties", {}).get("ipa_100", 0),
                reverse=True,
            )[:5]
            if top5:
                parts.append("\nTOP-5 PRESSURE HOTSPOTS (IPA Score):")
                for i, feat in enumerate(top5, 1):
                    p = feat.get("properties", {})
                    parts.append(
                        f"  {i}. Cell {p.get('h3_index','N/A')}: "
                        f"IPA={p.get('ipa_100', 0):.1f}/100 [{p.get('ipa_level','N/A')}] "
                        f"| vessels={p.get('vessel_count', 0)} | ais_gaps={p.get('gap_count', 0)}"
                    )
        except Exception as exc:
            logger.warning("[Memory] No se pudo leer hotspots: %s", exc)

    # Gap events
    def _count_json(path: str, label: str, extra: Optional[callable] = None) -> None:
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data = json.load(f)
            msg = f"{label}: {len(data)}"
            if extra:
                msg += extra(data)
            parts.append(msg)
        except Exception:
            pass

    _count_json(
        "data/gfw_gap_events_cache.json",
        "GAP EVENTS SUMMARY",
        lambda d: f" total | {sum(1 for g in d if g.get('gap_hours', 0) > 24)} lasting >24h",
    )
    _count_json("data/gfw_encounters_cache.json", "ENCOUNTER EVENTS")
    _count_json("data/gfw_loitering_cache.json",  "LOITERING EVENTS")

    # Estacionalidad
    try:
        from src.pipeline.seasonal import compute_seasonal_summary
        season = compute_seasonal_summary(datetime.now().month)
        parts.append(
            f"\nCURRENT SEASON (month={datetime.now().month}): "
            f"{season['season_label']} | pressure_modifier={season['pressure_modifier']} "
            f"| level={season['pressure_level']} | is_veda={season['is_veda']}"
        )
    except Exception:
        pass

    return "\n".join(parts)


# ── CAPA 3: PROMPT ENGINEERING ───────────────────────────────────────────────

def analyze_hotspot(
    h3_index:     str,
    ipa_score:    float,
    vessel_count: int,
    gap_count:    int = 0,
    enc_count:    int = 0,
    loi_count:    int = 0,
    month:        Optional[int] = None,
) -> dict:
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
  "confidence": "HIGH | MEDIUM | LOW",
  "data_quality_notes": "any limitations of GFW-only analysis for this cell"
}}"""
    return _parse_json_response(_call_gemini(prompt, context=context))


def synthesize_region(top_n: int = 5) -> dict:
    context = build_pipeline_memory()
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

Current analysis month: {datetime.now().month}
Top {top_n} hotspots analyzed from the IPA index."""
    return _parse_json_response(_call_gemini(prompt, context=context))


def explain_ipa_for_paper() -> str:
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
    t0 = time.time()
    response = _call_gemini('Respond with exactly: {"status": "ok", "model": "gemini-2.5-flash"}')
    latency_ms = int((time.time() - t0) * 1000)
    result = _parse_json_response(response)
    result["latency_ms"] = latency_ms
    result["available"]  = result.get("status") == "ok"
    return result
