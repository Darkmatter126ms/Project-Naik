"use client";

/**
 * useRealtimeVoice — production WebRTC voice capture for the intake page.
 *
 * Connects to the OpenAI Realtime API (GA WebRTC interface), streams mic audio,
 * accumulates the Bahasa Indonesia transcript of the USER'S speech, auto-stops
 * after `maxSeconds` (default 90), and closes cleanly. Returns transcript text
 * via the onTranscript callback and exposes start/stop + status.
 *
 * Token security: the ephemeral key is minted by the Flask backend at
 * `${API_BASE}/realtime/token`. The real OpenAI key never reaches the browser.
 *
 * If anything fails (no key configured, mic denied, network), `error` is set
 * and the caller (intake page) falls back to manual transcript entry — so the
 * demo never hard-blocks on voice.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { Lang } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:5050";
// GA model name. MUST match the model the backend mints the token against
// (api/realtime.py REALTIME_MODEL / NAIK_REALTIME_MODEL) or the SDP call fails.
const REALTIME_MODEL =
  process.env.NEXT_PUBLIC_REALTIME_MODEL ?? "gpt-realtime";

export type VoiceStatus =
  | "idle"
  | "connecting"
  | "listening"
  | "stopped"
  | "error";

interface Options {
  maxSeconds?: number;
  lang?: Lang;
  onTranscript?: (full: string) => void;
  onTranscriptDelta?: (partial: string) => void;
  onError?: (message: string) => void;
}

function normalizeTranscript(text: string): string {
  const cleaned = text
    .normalize("NFKD")
    .replace(/[^\p{Script=Latin}\p{N}\p{P}\p{Zs}]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();

  return cleaned;
}

export function useRealtimeVoice({
  maxSeconds = 90,
  lang = "id",
  onTranscript,
  onTranscriptDelta,
  onError,
}: Options = {}) {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [secondsLeft, setSecondsLeft] = useState(maxSeconds);
  const [transcript, setTranscript] = useState("");

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const transcriptRef = useRef("");

  const cleanup = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    try { dcRef.current?.close(); } catch { /* ignore */ }
    try { streamRef.current?.getTracks().forEach((t) => t.stop()); } catch { /* ignore */ }
    try { pcRef.current?.close(); } catch { /* ignore */ }
    dcRef.current = null;
    streamRef.current = null;
    pcRef.current = null;
  }, []);

  const stop = useCallback(() => {
    cleanup();
    setStatus("stopped");
    setSecondsLeft(0);
    onTranscript?.(transcriptRef.current);
  }, [cleanup, onTranscript]);

  const fail = useCallback(
    (message: string) => {
      cleanup();
      setStatus("error");
      onError?.(message);
    },
    [cleanup, onError],
  );

  const start = useCallback(async () => {
    try {
      setStatus("connecting");
      setTranscript("");
      transcriptRef.current = "";
      setSecondsLeft(maxSeconds);

      // 1. Ephemeral token (server-minted).
      const tokenRes = await fetch(`${API_BASE}/realtime/token`, {
        method: "POST",
      });
      if (!tokenRes.ok) throw new Error(`token endpoint ${tokenRes.status}`);
      const data = await tokenRes.json();
      const ephemeral = data.value ?? data.client_secret?.value ?? data.client_secret;
      if (!ephemeral) {
        console.error("[useRealtimeVoice] token response:", data);
        throw new Error("no ephemeral token returned — check Render logs for OPENAI_API_KEY / endpoint issues");
      }

      // 2. Mic.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // 3. Peer connection + data channel.
      const pc = new RTCPeerConnection();
      pcRef.current = pc;

      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "failed" || pc.connectionState === "disconnected") {
          fail("Realtime connection dropped. Check network and try again.");
        }
      };

      pc.addTrack(stream.getAudioTracks()[0], stream);

      const dc = pc.createDataChannel("oai-events");
      dcRef.current = dc;

      dc.onopen = () => {
        setStatus("listening");
        // GA session.update shape: transcription + VAD live under audio.input.
        // (Pre-GA used top-level input_audio_transcription / turn_detection.)
        dc.send(
          JSON.stringify({
            type: "session.update",
            session: {
              type: "realtime",
              instructions:
                "Anda hanya mendengarkan wawancara keuangan; jangan menjawab.",
                audio: {
                  input: {
                    transcription: {
                      model: "gpt-4o-transcribe",
                      language: lang,
                    },
                    turn_detection: { type: "server_vad" },
                  },
                },
            },
          }),
        );
        // 90-second hard cap.
        timerRef.current = setInterval(() => {
          setSecondsLeft((s) => {
            if (s <= 1) {
              stop();
              return 0;
            }
            return s - 1;
          });
        }, 1000);
      };

      dc.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (
          msg.type ===
          "conversation.item.input_audio_transcription.completed"
        ) {
          const normalized = normalizeTranscript(msg.transcript ?? "");
          transcriptRef.current =
            (transcriptRef.current ? transcriptRef.current + " " : "") +
            normalized;
          setTranscript(transcriptRef.current);
          onTranscript?.(transcriptRef.current);
        } else if (
          msg.type === "conversation.item.input_audio_transcription.delta"
        ) {
          const normalizedDelta = normalizeTranscript(msg.delta ?? "");
          const live = transcriptRef.current
            ? transcriptRef.current + " " + normalizedDelta
            : normalizedDelta;
          onTranscriptDelta?.(live);
        } else if (msg.type === "error") {
          fail(msg.error?.message ?? "realtime error");
        }
      };

      // 4. SDP exchange.
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const sdpRes = await fetch(
        `https://api.openai.com/v1/realtime/calls?model=${REALTIME_MODEL}`,
        {
          method: "POST",
          body: offer.sdp,
          headers: {
            Authorization: `Bearer ${ephemeral}`,
            "Content-Type": "application/sdp",
          },
        },
      );
      if (!sdpRes.ok) {
        const errBody = await sdpRes.text().catch(() => "");
        throw new Error(`SDP exchange ${sdpRes.status}${errBody ? ": " + errBody.slice(0, 120) : ""}`);
      }
      await pc.setRemoteDescription({
        type: "answer",
        sdp: await sdpRes.text(),
      });
    } catch (err) {
      const msg = (err as Error).message;
      fail(
        /permission|denied|not allowed/i.test(msg)
          ? "Microphone access is blocked. Allow mic in browser settings, or use the cached audio button instead."
          : msg,
      );
    }
  }, [maxSeconds, stop, fail]);

  // Cleanup on unmount.
  useEffect(() => cleanup, [cleanup]);

  return { status, secondsLeft, transcript, start, stop };
}
