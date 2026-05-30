/**
 * lib/vigia/fetcher.ts — Fetch wrapper con caché nativo de Next.js.
 *
 * Envuelve `fetch` con:
 * - `next: { revalidate }` configurable
 * - Manejo de errores que retorna `{ data: null, error }` en vez de lanzar
 * - Inyección automática de auth headers para GFW
 */

import { GFW_BASE_URL } from "./config";

// ─── Types ───────────────────────────────────────────────────

export interface FetchResult<T> {
  data: T | null;
  error: string | null;
}

interface SafeFetchOptions {
  /** Cache revalidation in seconds (Next.js ISR). */
  revalidate: number;
  /** Extra headers to merge. */
  headers?: Record<string, string>;
}

// ─── GFW Token ───────────────────────────────────────────────

function getGfwToken(): string | undefined {
  return process.env.GFW_API_TOKEN;
}

/**
 * Builds the appropriate headers for a URL.
 * Auto-injects Bearer token for GFW API calls.
 */
function buildHeaders(
  url: string,
  extra?: Record<string, string>
): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...extra,
  };

  // Auto-inject GFW auth
  if (url.startsWith(GFW_BASE_URL)) {
    const token = getGfwToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  return headers;
}

// ─── Core Fetcher ────────────────────────────────────────────

/**
 * Performs a cached GET request. Returns `{ data, error }` — never throws.
 *
 * Uses Next.js native `next: { revalidate }` for ISR-style caching,
 * so the response is served from cache and revalidated in the background.
 *
 * @example
 * const { data, error } = await safeFetch<MyType>(url, { revalidate: 3600 });
 * if (error) return degradedResponse(error);
 */
export async function safeFetch<T>(
  url: string,
  options: SafeFetchOptions
): Promise<FetchResult<T>> {
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: buildHeaders(url, options.headers),
      next: { revalidate: options.revalidate },
    });

    if (!res.ok) {
      const body = await res.text().catch(() => "");
      const msg = `[Vigia] ${res.status} ${res.statusText} — ${url.split("?")[0]}`;
      console.warn(msg, body.slice(0, 200));
      return { data: null, error: `HTTP ${res.status}: ${res.statusText}` };
    }

    const data = (await res.json()) as T;
    return { data, error: null };
  } catch (err) {
    const msg =
      err instanceof Error ? err.message : "Unknown network error";
    console.error(`[Vigia] Fetch failed — ${url.split("?")[0]}:`, msg);
    return { data: null, error: msg };
  }
}

/**
 * Convenience: fetch multiple URLs in parallel, return all results.
 */
export async function safeFetchAll<T>(
  urls: string[],
  options: SafeFetchOptions
): Promise<FetchResult<T>[]> {
  return Promise.all(urls.map((u) => safeFetch<T>(u, options)));
}
