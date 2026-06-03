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

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:5050";
const REALTIME_MODEL = "gpt-realtime";

export type VoiceStatus =
  | "idle"
  | "connecting"
  | "listening"
  | "stopped"
  | "error";

interface Options {
  maxSeconds?: number;
  onTranscript?: (full: string) => void;
  onError?: (message: string) => void;
}

export function useRealtimeVoice({
  maxSeconds = 90,
  onTranscript,
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
    dcRef.current?.close();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    pcRef.current?.close();
    dcRef.current = null;
    streamRef.current = null;
    pcRef.current = null;
  }, []);

  const stop = useCallback(() => {
    cleanup();
    setStatus("stopped");
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
      const ephemeral = data.client_secret?.value ?? data.client_secret;
      if (!ephemeral) throw new Error("no ephemeral token returned");

      // 2. Mic.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // 3. Peer connection + data channel.
      const pc = new RTCPeerConnection();
      pcRef.current = pc;
      pc.addTrack(stream.getAudioTracks()[0], stream);

      const dc = pc.createDataChannel("oai-events");
      dcRef.current = dc;

      dc.onopen = () => {
        setStatus("listening");
        dc.send(
          JSON.stringify({
            type: "session.update",
            session: {
              instructions:
                "Anda hanya mendengarkan wawancara keuangan; jangan menjawab.",
              input_audio_transcription: {
                model: "gpt-4o-transcribe",
                language: "id",
              },
              turn_detection: { type: "server_vad" },
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
          transcriptRef.current =
            (transcriptRef.current ? transcriptRef.current + " " : "") +
            msg.transcript;
          setTranscript(transcriptRef.current);
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
      if (!sdpRes.ok) throw new Error(`SDP exchange ${sdpRes.status}`);
      await pc.setRemoteDescription({
        type: "answer",
        sdp: await sdpRes.text(),
      });
    } catch (err) {
      fail((err as Error).message);
    }
  }, [maxSeconds, stop, fail]);

  // Cleanup on unmount.
  useEffect(() => cleanup, [cleanup]);

  return { status, secondsLeft, transcript, start, stop };
}
