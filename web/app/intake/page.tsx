"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { COPY } from "@/lib/copy";
import { useLang } from "@/lib/useLang";
import { useTheme } from "@/lib/useTheme";
import {
  SARI_PERSONA_BASE,
  PERSONA_TRANSCRIPTS,
  CACHED_VOICE_INTAKES,
  type CachedVoiceIntake,
} from "@/lib/fixtures";
import { ApiError, postOrchestrate } from "@/lib/api";
import { useRealtimeVoice } from "@/lib/useRealtimeVoice";

const DURATION = 90;
type RecordState = "idle" | "recording" | "done";

export default function IntakePage() {
  const [lang, setLang] = useLang();
  const [theme, toggleTheme] = useTheme();
  const [state, setState] = useState<RecordState>("idle");
  const [secondsLeft, setSecondsLeft] = useState(DURATION);
  const [transcript, setTranscript] = useState("");
  const [cachedId, setCachedId] = useState<string | null>(null);
  const [activePersonaId, setActivePersonaId] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const t = COPY[lang];
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Hilda: dedicated refs for cached audio cleanup
  const cachedAudioRef = useRef<HTMLAudioElement | null>(null);
  const cachedTimelineRef = useRef<number[]>([]);

  // ── Realtime voice (Hilda H-1-2) ─────────────────────────────────────────
  const {
    status: voiceStatus,
    secondsLeft: realtimeSecondsLeft,
    transcript: realtimeTranscript,
    start,
    stop,
  } = useRealtimeVoice({
    maxSeconds: DURATION,
    lang,
    onTranscript: (full) => {
      setTranscript(full);
      setState("done");
    },
    onTranscriptDelta: (partial) => setTranscript(partial),
    onError: (message) => setError(message),
  });

  useEffect(() => {
    if (realtimeTranscript) setTranscript(realtimeTranscript);
  }, [realtimeTranscript]);

  useEffect(() => {
    if (voiceStatus === "listening") setState("recording");
    else if (voiceStatus === "stopped" && transcript.trim()) setState("done");
  }, [voiceStatus, transcript]);

  // ── Persona pre-fill (your code) ──────────────────────────────────────────
  // When coming from the home page, pre-fill the canonical transcript for
  // sari / budi / aisyah so Analyse Now is immediately available.
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem("naik_persona");
      if (!stored) return;
      const persona = JSON.parse(stored) as { user_id?: string };
      const id = persona.user_id ?? null;
      setActivePersonaId(id);
      if (id && PERSONA_TRANSCRIPTS[id]) {
        setTranscript(PERSONA_TRANSCRIPTS[id]);
        setState("done");
      }
    } catch { /* malformed sessionStorage */ }
  }, []);

  // ── Timer / recording helpers ─────────────────────────────────────────────
  const stopRecording = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    stop();
    setState("done");
  }, [stop]);

  const startCountdown = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          clearInterval(timerRef.current!);
          timerRef.current = null;
          return 0;
        }
        return s - 1;
      });
    }, 1000);
  }, []);

  async function startRecording() {
    setState("recording");
    setTranscript("");
    setError(null);
    try {
      startCountdown();
      await start();
    } catch {
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = null;
      setError("Unable to start realtime voice capture.");
      setState("idle");
    }
  }

  // Cleanup on unmount
  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current); }, []);
  useEffect(() => {
    return () => {
      if (cachedAudioRef.current) {
        cachedAudioRef.current.pause();
        cachedAudioRef.current.src = "";
        cachedAudioRef.current = null;
      }
      cachedTimelineRef.current.forEach(clearTimeout);
      cachedTimelineRef.current = [];
    };
  }, []);

  // ── Cached audio (Hilda H-3-2) ────────────────────────────────────────────
  // Which CACHED_VOICE_INTAKE is currently selected (for active-button styling)
  const selectedCached = useMemo(
    () => CACHED_VOICE_INTAKES.find((item) => item.id === cachedId) ?? null,
    [cachedId],
  );

  // The single cached intake that matches the current active persona.
  // sari → sari-canonical, budi → male-younger-lower-income, aisyah → female-older-halal
  // null when the user came via /onboard (no recognised persona id).
  const cachedForPersona = useMemo(
    () =>
      activePersonaId
        ? (CACHED_VOICE_INTAKES.find(
            (item) => (item.persona as Record<string, unknown>).user_id === activePersonaId,
          ) ?? null)
        : null,
    [activePersonaId],
  );

  // Live transcript: during cached playback, reveal segments in sync with audio
  const liveTranscript = useMemo(() => {
    if (!selectedCached || state !== "recording") return transcript;
    const elapsed =
      DURATION * 1000 -
      (voiceStatus === "listening" ? realtimeSecondsLeft : secondsLeft) * 1000;
    let acc = 0;
    const visible: string[] = [];
    for (const seg of selectedCached.transcriptSegments) {
      acc += seg.durationMs;
      if (elapsed >= acc) visible.push(seg.text);
    }
    return visible.join(" ") || transcript;
  }, [selectedCached, state, transcript, voiceStatus, realtimeSecondsLeft, secondsLeft]);

  async function useCachedAudio(item: CachedVoiceIntake) {
    setCachedId(item.id);
    setError(null);

    // Tear down any previous cached playback
    if (cachedAudioRef.current) {
      cachedAudioRef.current.pause();
      cachedAudioRef.current.src = "";
    }
    cachedTimelineRef.current.forEach(clearTimeout);
    cachedTimelineRef.current = [];

    setState("recording");
    setTranscript("");
    setSecondsLeft(DURATION);

    // Set the persona from the intake item so analysis uses the right base
    sessionStorage.setItem("naik_persona", JSON.stringify(item.persona));

    try {
      const audio = new Audio(item.audioSrc);
      cachedAudioRef.current = audio;

      // Build cumulative reveal delays for each segment
      const revealDelays = item.transcriptSegments.reduce<number[]>(
        (acc, seg, i) => { acc.push((acc[i - 1] ?? 0) + seg.durationMs); return acc; },
        [],
      );

      // Schedule word-by-word transcript reveal
      let revealed: string[] = [];
      item.transcriptSegments.forEach((seg, i) => {
        const tid = window.setTimeout(() => {
          revealed = [...revealed, seg.text];
          setTranscript(revealed.join(" "));
        }, revealDelays[i]);
        cachedTimelineRef.current.push(tid);
      });

      audio.onplay  = () => setState("recording");
      audio.onended = () => {
        if (timerRef.current) clearInterval(timerRef.current);
        timerRef.current = null;
        setTranscript(item.transcript);
        setState("done");
    };

      startCountdown();
      await audio.play();
    } catch {
      // Audio playback blocked (e.g. autoplay policy) — fill transcript silently
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = null;
      setTranscript(item.transcript);
      setState("done");
    }
  }

  // ── Analysis (your code — keeps naik_persona_input for issuance flow) ─────
  async function handleAnalyze() {
    if (!transcript.trim()) return;
    setAnalyzing(true);
    setError(null);

    // Stop any still-playing cached audio before navigating
    if (cachedAudioRef.current) {
      cachedAudioRef.current.pause();
      cachedAudioRef.current = null;
    }

    try {
      const stored = sessionStorage.getItem("naik_persona");
      const personaBase = stored ? JSON.parse(stored) : SARI_PERSONA_BASE;

      const result = await postOrchestrate({
        ...personaBase,
        voice_transcript: transcript.trim(),
      });

      // Persist for the issuance flow (POST /issue needs persona identity)
      sessionStorage.setItem("naik_persona_input", JSON.stringify({
        ...personaBase,
        voice_transcript: transcript.trim(),
      }));
      sessionStorage.setItem("naik_result", JSON.stringify(result));
      router.push("/results");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Terjadi kesalahan saat memproses. Silakan coba lagi.",
      );
      setAnalyzing(false);
    }
  }

  // ── SVG ring progress ─────────────────────────────────────────────────────
  const R = 52;
  const C = 2 * Math.PI * R;
  const progress =
    state === "recording"
      ? (DURATION - secondsLeft) / DURATION
      : 0;
  const dash = C - progress * C;
  const displaySeconds = secondsLeft;

  return (
    <div className="page page--intake">
      <div className="lang-toggle">
        <button className="lang-btn" onClick={toggleTheme} aria-label="Toggle colour theme">
          {theme === "dark" ? "☀" : "🌙"}
        </button>
        <button className="lang-btn" onClick={() => setLang(lang === "id" ? "en" : "id")}>
          {t.langToggle}
        </button>
      </div>

      <button className="back-link" onClick={() => router.push("/")}>
        {t.backToHome}
      </button>

      <h1 className="page-title">{t.intakeTitle}</h1>
      <p className="page-subtitle">{t.intakeInstruction}</p>

      <div className="intake-pointers" aria-label="Voice intake guidance">
        <h2 className="intake-pointers__title">{t.intakePointersTitle}</h2>
        <ul className="intake-pointers__list">
          <li>{t.intakePointersJob}</li>
          <li>{t.intakePointersLocation}</li>
          <li>
            {t.intakePointersFinancialTitle}
            <ul className="intake-pointers__sublist">
              <li>{t.intakePointersFinancialItem1}</li>
              <li>{t.intakePointersFinancialItem2}</li>
              <li>{t.intakePointersFinancialItem3}</li>
              <li>{t.intakePointersFinancialItem4}</li>
              <li>{t.intakePointersFinancialItem5}</li>
            </ul>
          </li>
        </ul>
      </div>

      {/* ── Single cached-audio button — persona-aware (Hilda H-3-2) ───────
           Only shown when the user arrived via a demo persona card.
           One button per persona: clicking loads that persona's MP3 and
           animates the transcript.  Label uses the existing locale key so
           it stays bilingual.  Hidden for custom /onboard users. ── */}
      {cachedForPersona && (
        <div className="cached-audio-wrap">
          <button
            className={`btn btn--outline cached-audio-btn${cachedId === cachedForPersona.id ? " cached-audio-btn--active" : ""}`}
            onClick={() => useCachedAudio(cachedForPersona)}
            disabled={analyzing}
            type="button"
          >
            ▶ {t.useCachedAudio}
          </button>
          <p className="cached-audio-hint">{t.useCachedAudioHint}</p>
        </div>
      )}

      {error && (
        <div className="error-toast" role="alert">
          <span>⚠ {error}</span>
          <button className="error-toast__close" onClick={() => setError(null)} aria-label={t.close}>✕</button>
        </div>
      )}

      {/* ── Voice ring ── */}
      <div className="voice-ring-wrap">
        <svg className="voice-ring" viewBox="0 0 120 120" width="120" height="120">
          <circle cx="60" cy="60" r={R} fill="none" stroke="var(--line)" strokeWidth="3" />
          <circle
            cx="60" cy="60" r={R} fill="none"
            stroke={state === "recording" ? "var(--signal)" : "var(--line)"}
            strokeWidth="3"
            strokeDasharray={C}
            strokeDashoffset={dash}
            strokeLinecap="round"
            transform="rotate(-90 60 60)"
            style={{ transition: "stroke-dashoffset 1s linear" }}
          />
        </svg>

        <button
          className={`voice-btn${state === "recording" ? " voice-btn--active" : ""}`}
          onClick={state === "recording" ? stopRecording : startRecording}
          disabled={analyzing}
          aria-label={state === "recording" ? t.recordStop : t.recordStart}
        >
          <span className={`voice-btn__icon${state === "recording" ? " voice-btn__icon--stop" : ""}`}>
            {state === "recording" ? "■" : "🎙"}
          </span>
        </button>

        <p className="voice-countdown" aria-live="polite" aria-atomic="true">
          <span className="voice-countdown__num">{displaySeconds}</span>
          <span className="voice-countdown__label"> {t.timeLeft}</span>
        </p>
      </div>

      {/* ── Transcript ── */}
      <div className="transcript-wrap">
        <label className="transcript-label">{t.transcriptLabel}</label>
        <textarea
          className="transcript-area"
          value={liveTranscript}
          onChange={(e) => setTranscript(e.target.value)}
          placeholder={t.transcriptPlaceholder}
          rows={6}
          spellCheck={false}
        />
      </div>

      {state === "done" && transcript.trim() && (
        <div className="cta-center">
          <button
            className="btn btn--primary btn--wide"
            onClick={handleAnalyze}
            disabled={analyzing}
          >
            {analyzing ? t.analyzing : t.analyzeBtn}
          </button>
        </div>
      )}
    </div>
  );
}
