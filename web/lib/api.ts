// Thin client for the Naik API. The base URL is read from the public env var
// (inlined at build time by Next). All calls are client-side for this proof.

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
