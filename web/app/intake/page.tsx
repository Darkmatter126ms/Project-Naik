"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { COPY } from "@/lib/copy";
import { FIXTURE_RESULT } from "@/lib/fixtures";
import type { Lang } from "@/lib/types";

const DURATION = 90; // seconds

type RecordState = "idle" | "recording" | "done";

export default function IntakePage() {
  const [lang, setLang] = useState<Lang>("id");
  const [state, setState] = useState<RecordState>("idle");
  const [secondsLeft, setSecondsLeft] = useState(DURATION);
  const [transcript, setTranscript] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const router = useRouter();
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const t = COPY[lang];

  // Check if Sari was pre-selected on the home page
  useEffect(() => {
    const selected = sessionStorage.getItem("selected_persona");
    if (selected === "sari") {
      // Pre-fill with Sari's canonical transcript (Bahasa)
      setTranscript(
        "Dulu saya pernah beli reksa dana di Bibit lewat Shopee, tapi cuma sekali lalu saya tinggal begitu saja. " +
          "Saya tidak punya asuransi apa pun. Saya kerja sebagai driver ojek online, jadi kalau banjir dan saya " +
          "tidak bisa keluar, penghasilan saya langsung berhenti — saya tidak terlindungi sama sekali. " +
          "Saya menabung sedikit, tapi sering tergoda checkout kalau ada diskon.",
      );
      setState("done");
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    setState("done");
  }, []);

  function startRecording() {
    setState("recording");
    setSecondsLeft(DURATION);
    setTranscript("");
    timerRef.current = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          stopRecording();
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    // Block 2 (Hilda): wire live WebRTC here and stream transcript chunks
  }

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current); }, []);

  function handleAnalyze() {
    setAnalyzing(true);
    // Phase 2: POST to /orchestrate; for now use the fixture immediately
    setTimeout(() => {
      sessionStorage.setItem("naik_result", JSON.stringify(FIXTURE_RESULT));
      router.push("/results");
    }, 1400);
  }

  // Arc path for the countdown ring (r=52)
  const R = 52;
  const C = 2 * Math.PI * R;
  const progress = state === "recording" ? (DURATION - secondsLeft) / DURATION : 0;
  const dash = C - progress * C;

  return (
    <div className="page page--intake">
      <div className="lang-toggle">
        <button className="lang-btn" onClick={() => setLang(lang === "id" ? "en" : "id")}>
          {t.langToggle}
        </button>
      </div>

      <button className="back-link" onClick={() => router.push("/")}>
        {t.backToHome}
      </button>

      <h1 className="page-title">{t.intakeTitle}</h1>
      <p className="page-subtitle">{t.intakeInstruction}</p>

      {/* Voice button with animated ring */}
      <div className="voice-ring-wrap">
        <svg className="voice-ring" viewBox="0 0 120 120" width="120" height="120">
          {/* Background track */}
          <circle cx="60" cy="60" r={R} fill="none" stroke="var(--line)" strokeWidth="3" />
          {/* Progress arc — green during recording */}
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

      {/* Transcript area */}
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

      {/* Analyse button — enabled once there's a transcript */}
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
