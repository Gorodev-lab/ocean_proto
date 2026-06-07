"""
ocean_proto / src / pipeline / _resilience.py
=============================================
Módulo compartido de resiliencia HTTP.

Provee:
  - `http_get`  : GET síncrono con retry exponencial (para pipeline/background)
  - `http_post` : POST síncrono con retry exponencial
  - `retry`     : decorador tenacity preconfigurado para funciones síncronas

Uso:
    from src.pipeline._resilience import http_get, http_post

    data = http_get("https://api.example.com/v1/data", params={...}, timeout=20)
    # → dict con el JSON de respuesta, o None si todos los reintentos fallaron.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

# ── Configuración global ──────────────────────────────────────────────────────
_MAX_ATTEMPTS     = 3
_WAIT_MIN_SEC     = 1.0   # espera mínima entre reintentos
_WAIT_MAX_SEC     = 30.0  # espera máxima entre reintentos
_DEFAULT_TIMEOUT  = 20.0  # segundos

# Errores que justifican retry (transitorios)
_RETRIABLE = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)

# ── Decorador de retry reutilizable ──────────────────────────────────────────
retry_transient = retry(
    retry=retry_if_exception_type(_RETRIABLE),
    stop=stop_after_attempt(_MAX_ATTEMPTS),
    wait=wait_exponential(multiplier=1, min=_WAIT_MIN_SEC, max=_WAIT_MAX_SEC),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=False,
)


def _build_headers(token: str | None = None) -> dict[str, str]:
    """Construye headers estándar, con Bearer token opcional."""
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def http_get(
    url: str,
    *,
    params: dict | None = None,
    token: str | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
    raise_on_4xx: bool = True,
) -> dict | list | None:
    """
    GET síncrono con retry exponencial para errores transitorios.

    Returns
    -------
    dict | list | None
        Cuerpo JSON de la respuesta, o None si todos los intentos fallaron.
    """
    @retry_transient
    def _do() -> dict | list:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url, params=params, headers=_build_headers(token))
            if raise_on_4xx:
                r.raise_for_status()
            elif 400 <= r.status_code < 500:
                logger.error("[HTTP] %s %s → %d (no retry)", "GET", url, r.status_code)
                raise httpx.HTTPStatusError(
                    f"HTTP {r.status_code}", request=r.request, response=r
                )
            r.raise_for_status()
            return r.json()

    try:
        return _do()
    except Exception as exc:
        logger.error("[HTTP] GET %s falló tras %d intentos: %s", url, _MAX_ATTEMPTS, exc)
        return None


def http_post(
    url: str,
    *,
    json: Any = None,
    params: dict | None = None,
    token: str | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict | list | None:
    """
    POST síncrono con retry exponencial para errores transitorios.

    Returns
    -------
    dict | list | None
        Cuerpo JSON de la respuesta, o None si todos los intentos fallaron.
    """
    @retry_transient
    def _do() -> dict | list:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(
                url, json=json, params=params,
                headers=_build_headers(token),
            )
            r.raise_for_status()
            return r.json()

    try:
        return _do()
    except Exception as exc:
        logger.error("[HTTP] POST %s falló tras %d intentos: %s", url, _MAX_ATTEMPTS, exc)
        return None
