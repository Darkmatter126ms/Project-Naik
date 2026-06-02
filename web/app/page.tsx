"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE, pingHealth, type HealthResponse } from "@/lib/api";

type Lang = "id" | "en";

const COPY: Record<Lang, Record<string, string>> = {
  id: {
    eyebrow: "Lapisan agentik di dalam Monee",
    tagline:
      "Console status untuk membuktikan jalur cloud: frontend (Vercel) → backend (Render) → Postgres.",
    ping: "Periksa Koneksi",
    pinging: "Menghubungi…",
    target: "tujuan",
    idle: "Belum diperiksa. Tekan tombol untuk menghubungi backend.",
    status: "status",
    version: "versi",
    schema: "skema",
    db: "basis data",
    time: "waktu",
    okBanner: "Backend terjangkau ✓",
    notConfigured: "API belum dikonfigurasi.",
  },
  en: {
    eyebrow: "Agentic layer inside Monee",
    tagline:
      "Status console proving the cloud path: frontend (Vercel) → backend (Render) → Postgres.",
    ping: "Check Connection",
    pinging: "Contacting…",
    target: "target",
    idle: "Not checked yet. Hit the button to reach the backend.",
    status: "status",
    version: "version",
    schema: "schema",
    db: "database",
    time: "time",
    okBanner: "Backend reachable ✓",
    notConfigured: "API base URL not configured.",
  },
};

function dbClass(db: string): string {
  if (db === "ok") return "v--ok";
  if (db === "not_configured") return "v--warn";
  return "v--err";
}

export default function Home() {
  const [lang, setLang] = useState<Lang>("id");
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const t = COPY[lang];

  const run = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const data = await pingHealth(signal);
      setHealth(data);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setHealth(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  // Probe once on load so the cloud path is exercised without a click.
  useEffect(() => {
    const ctrl = new AbortController();
    if (API_BASE) void run(ctrl.signal);
    return () => ctrl.abort();
  }, [run]);

  const ok = health?.status === "ok";
  const dotClass = loading
    ? "dot"
    : error
      ? "dot dot--err"
      : ok
        ? "dot dot--ok"
        : "dot";

  return (
    <main>
      <p className="eyebrow">{t.eyebrow}</p>
      <h1 className="wordmark">
        Naik<span>.</span>
      </h1>
      <p className="tagline">{t.tagline}</p>

      <section className="panel" aria-live="polite">
        <div className="panel__bar">
          <span className={dotClass} aria-hidden />
          <span>GET /health</span>
          <span className="target" title={API_BASE || t.notConfigured}>
            {t.target}: {API_BASE || "—"}
          </span>
        </div>
        <div className="panel__body">
          {error ? (
            <p className="error">{error}</p>
          ) : !health ? (
            <p className="row">
              <span className="k">{loading ? t.pinging : t.idle}</span>
            </p>
          ) : (
            <>
              <div className="row">
                <span className="k">{t.status}</span>
                <span className={`v ${ok ? "v--ok" : "v--warn"}`}>
                  {health.status}
                </span>
              </div>
              <div className="row">
                <span className="k">{t.version}</span>
                <span className="v">{health.version}</span>
              </div>
              <div className="row">
                <span className="k">{t.schema}</span>
                <span className="v">{health.schema_version}</span>
              </div>
              <div className="row">
                <span className="k">{t.db}</span>
                <span className={`v ${dbClass(health.db)}`}>{health.db}</span>
              </div>
              <div className="row">
                <span className="k">{t.time}</span>
                <span className="v">{health.time}</span>
              </div>
            </>
          )}
        </div>
      </section>

      <div className="controls">
        <button className="btn" onClick={() => void run()} disabled={loading}>
          {loading ? t.pinging : t.ping}
        </button>
        <div className="toggle" role="group" aria-label="language">
          <button aria-pressed={lang === "id"} onClick={() => setLang("id")}>
            ID
          </button>
          <button aria-pressed={lang === "en"} onClick={() => setLang("en")}>
            EN
          </button>
        </div>
      </div>

      <p className="note">
        Set <code>NEXT_PUBLIC_API_BASE_URL</code> in Vercel to your Render URL.
      </p>
    </main>
  );
}
