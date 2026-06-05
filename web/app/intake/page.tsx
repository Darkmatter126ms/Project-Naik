"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { COPY } from "@/lib/copy";
import { useLang } from "@/lib/useLang";
import { useTheme } from "@/lib/useTheme";
import { SARI_PERSONA_BASE, PERSONA_AUDIO, PERSONA_TRANSCRIPTS } from "@/lib/fixtures";
import { ApiError, postOrchestrate } from "@/lib/api";


const DURATION = 90;
type RecordState = "idle" | "recording" | "done";

export default function IntakePage() {
  const [lang, setLang] = useLang();
  const [theme, toggleTheme] = useTheme();
  const [state, setState] = useState<RecordState>("idle");
  const [secondsLeft, setSecondsLeft] = useState(DURATION);
  const [transcript, setTranscript] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activePersonaId, setActivePersonaId] = useState<string | null>(null);
  const [playingAudio, setPlayingAudio] = useState(false);
  const router = useRouter();
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const t = COPY[lang];

  // Detect the active persona from sessionStorage on mount.
  // For demo personas (sari / budi / aisyah): pre-fill their canonical
  // transcript so the Analyze button is immediately ready.
  // For custom onboard users: the textarea starts empty — they speak or type.
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
    } catch { /* malformed sessionStorage — ignore */ }
  }, []);

  // Stop and release any playing audio when the component unmounts.
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, []);

  const stopRecording = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    setState("done");
  }, []);

  function startRecording() {
    // Stop cached audio if it was playing before the user taps the mic.
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
      setPlayingAudio(false);
    }
    setState("recording");
    setSecondsLeft(DURATION);
    setTranscript("");
    timerRef.current = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) { stopRecording(); return 0; }
        return s - 1;
      });
    }, 1000);
  }

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current); }, []);

  /**
   * Play the persona's cached MP3 (so judges can hear the voice input) and
   * simultaneously fill the canonical transcript into the textarea so the
   * pipeline receives the same text it would get from live transcription.
   *
   * This function intentionally does NOT call handleAnalyze — the user still
   * taps "Analisis" to submit, keeping the flow identical to the live-voice path.
   */
  function playCachedAudio() {
    if (!activePersonaId) return;
    const audioPath = PERSONA_AUDIO[activePersonaId];
    const tx       = PERSONA_TRANSCRIPTS[activePersonaId];
    if (!audioPath || !tx) return;

    // Fill the transcript and make the Analyze button visible.
    setTranscript(tx);
    setState("done");

    // Stop any previously playing audio before starting a new one.
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    const audio = new Audio(audioPath);
    audioRef.current = audio;
    setPlayingAudio(true);

    audio.addEventListener("ended", () => setPlayingAudio(false));
    audio.addEventListener("error", () => setPlayingAudio(false));

    // play() returns a Promise; catch silently if autoplay is blocked.
    // The transcript is already filled regardless — the demo still works.
    audio.play().catch(() => setPlayingAudio(false));
  }

  async function handleAnalyze() {
    if (!transcript.trim()) return;
    setAnalyzing(true);
    setError(null);

    // Stop audio playback when the user submits — no overlap with results page.
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
      setPlayingAudio(false);
    }

    try {
      // Use the persona stored by the home page (Sari / Budi / Aisyah) or the
      // onboard form (custom user). Fall back to SARI_PERSONA_BASE only if
      // sessionStorage is unexpectedly empty (e.g. direct URL navigation).
      const stored = sessionStorage.getItem("naik_persona");
      const personaBase = stored ? JSON.parse(stored) : SARI_PERSONA_BASE;

      const result = await postOrchestrate({
        ...personaBase,
        voice_transcript: transcript.trim(),
      });
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

  const hasCachedAudio =
    !!activePersonaId && !!PERSONA_AUDIO[activePersonaId];

  const R = 52;
  const C = 2 * Math.PI * R;
  const progress = state === "recording" ? (DURATION - secondsLeft) / DURATION : 0;
  const dash = C - progress * C;

  return (
    <div className="page page--intake">
      <div className="lang-toggle">
        <button
          className="lang-btn"
          onClick={toggleTheme}
          aria-label="Toggle colour theme"
        >
          {theme === "dark" ? "☀" : "🌙"}
        </button>
        <button
          className="lang-btn"
          onClick={() => setLang(lang === "id" ? "en" : "id")}
        >
          {t.langToggle}
        </button>
      </div>

      <button className="back-link" onClick={() => router.push("/")}>
        {t.backToHome}
      </button>

      <h1 className="page-title">{t.intakeTitle}</h1>
      <p className="page-subtitle">{t.intakeInstruction}</p>

      {/* Error toast */}
      {error && (
        <div className="error-toast" role="alert">
          <span>⚠ {error}</span>
          <button
            className="error-toast__close"
            onClick={() => setError(null)}
            aria-label={t.close}
          >
            ✕
          </button>
        </div>
      )}

      <div className="voice-ring-wrap">
        <svg className="voice-ring" viewBox="0 0 120 120" width="120" height="120">
          <circle cx="60" cy="60" r={R} fill="none" stroke="var(--line)" strokeWidth="3" />
          <circle
            cx="60" cy="60" r={R}
            fill="none"
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
          className={`voice-btn ${state === "recording" ? "voice-btn--active" : ""}`}
          onClick={state === "recording" ? stopRecording : startRecording}
          disabled={analyzing}
          aria-label={state === "recording" ? t.recordStop : t.recordStart}
        >
          {state === "recording" ? (
            <span className="voice-btn__icon voice-btn__icon--stop">■</span>
          ) : (
            <span className="voice-btn__icon">🎙</span>
          )}
        </button>

        {state === "recording" && (
          <p className="voice-countdown">
            <span className="voice-countdown__num">{secondsLeft}</span>
            <span className="voice-countdown__label"> {t.timeLeft}</span>
          </p>
        )}
      </div>

      {/* Cached audio shortcut — only shown in idle state for the three demo
          personas. Hidden for custom onboard users and during recording. */}
      {state === "idle" && hasCachedAudio && (
        <div className="cached-audio-wrap">
          <button
            className={`btn btn--ghost btn--cached-audio ${playingAudio ? "btn--playing" : ""}`}
            onClick={playCachedAudio}
            disabled={analyzing}
            aria-label={t.useCachedAudio}
          >
            <span className="cached-audio-icon">
              {playingAudio ? "▶" : "▶"}
            </span>
            {playingAudio ? t.audioPlaying : t.useCachedAudio}
          </button>
          <p className="cached-audio-hint">
            {t.useCachedAudioHint}
          </p>
        </div>
      )}

      <div className="transcript-wrap">
        <label className="transcript-label">{t.transcriptLabel}</label>
        <textarea
          className="transcript-area"
          value={transcript}
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
