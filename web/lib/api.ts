// Thin client for the Naik API. The base URL is read from the public env var
// (inlined at build time by Next). All calls are client-side for this proof.

import type { FinalResponse } from "./types";

export const API_BASE: string =
  (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/+$/, "");

export interface HealthResponse {
  service: string;
  status: string;
  version: string;
  schema_version: string;
  time: string;
  db: "ok" | "not_configured" | "error" | string;
}

export class ApiError extends Error {}

/** Fetch the backend's /health. Throws ApiError on transport/HTTP failure. */
export async function pingHealth(signal?: AbortSignal): Promise<HealthResponse> {
  if (!API_BASE) {
    throw new ApiError(
      "NEXT_PUBLIC_API_BASE_URL is not set. Configure it in Vercel project settings.",
    );
  }
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/health`, { cache: "no-store", signal });
  } catch (err) {
    throw new ApiError(`Network error reaching ${API_BASE}/health: ${String(err)}`);
  }
  if (!resp.ok) {
    throw new ApiError(`Backend returned HTTP ${resp.status} from /health`);
  }
  return (await resp.json()) as HealthResponse;
}

/**
 * POST a DiagnosticInput-shaped payload to /orchestrate and return the
 * validated FinalResponse. Throws ApiError on network failure, non-2xx
 * status, or missing API_BASE. The payload must contain at minimum:
 *   user_id, age, monthly_income_idr, kecamatan, risk_tolerance
 * plus either voice_transcript or at least one transaction
 * (the backend's do-no-harm validator requires one signal).
 */
export async function postOrchestrate(
  payload: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<FinalResponse> {
  if (!API_BASE) {
    throw new ApiError(
      "NEXT_PUBLIC_API_BASE_URL is not set. Configure it in Vercel project settings.",
    );
  }
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/orchestrate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal,
    });
  } catch (err) {
    throw new ApiError(
      `Tidak dapat terhubung ke server (${String(err)}). Periksa koneksi internet Anda.`,
    );
  }
  if (!resp.ok) {
    let detail = "";
    try {
      const body = await resp.json();
      detail = body.detail ?? body.error ?? "";
    } catch {
      /* ignore parse error */
    }
    throw new ApiError(
      `Server mengembalikan HTTP ${resp.status}${detail ? `: ${detail}` : ""}`,
    );
  }
  return (await resp.json()) as FinalResponse;
}
