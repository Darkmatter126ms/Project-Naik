"use client";

/**
 * scratch/voice-test.tsx — THROWAWAY Realtime API spike (Block 2, Hilda).
 *
 * Purpose: prove we can (1) mint an ephemeral token, (2) open a WebRTC session,
 * (3) stream mic audio, (4) receive Bahasa Indonesia transcripts on the data
 * channel, and (5) close cleanly. Findings written to
 * design/realtime-api-notes.md.
 *
 * This is NOT production code. The reusable version lives in
 * web/lib/useRealtimeVoice.ts and is wired into app/intake/page.tsx.
 *
 * Run: drop this at app/scratch/page.tsx temporarily, set
 * NEXT_PUBLIC_API_BASE_URL, ensure the Flask /realtime/token endpoint is up,
 * then open /scratch and watch the console.
 */

import { useRef, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:5050";

// GA Realtime model (per build plan: gpt-realtime; mini is the cheaper option).
const REALTIME_MODEL = "gpt-realtime";

export default function VoiceTest() {
  const [status, setStatus] = useState("idle");
  const [transcript, setTranscript] = useState("");
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  async function start() {
    try {
      setStatus("minting token");
      // 1. Ephemeral token — minted SERVER-SIDE (never expose the real key).
      const tokenRes = await fetch(`${API_BASE}/realtime/token`, {
        method: "POST",
      });
      if (!tokenRes.ok) throw new Error(`token endpoint ${tokenRes.status}`);
      const { client_secret } = await tokenRes.json();
      const EPHEMERAL = client_secret?.value ?? client_secret;

      setStatus("getting mic");
      // 2. Microphone.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // 3. Peer connection.
      const pc = new RTCPeerConnection();
      pcRef.current = pc;

      // Remote audio (the model's voice) — not needed for transcription-only,
      // but wiring it proves the track negotiation works.
      pc.ontrack = (e) => {
        const el = new Audio();
        el.srcObject = e.streams[0];
        el.play().catch(() => {});
      };

      // Local mic track.
      pc.addTrack(stream.getAudioTracks()[0], stream);

      // 4. Data channel for events (transcripts arrive here).
      const dc = pc.createDataChannel("oai-events");
      dcRef.current = dc;

      dc.onopen = () => {
        setStatus("connected");
        // Configure the session: Bahasa Indonesia transcription of the USER'S
        // own speech, server VAD so we don't manage turn-taking manually.
        dc.send(
          JSON.stringify({
            type: "session.update",
            session: {
              instructions:
                "Anda adalah pewawancara keuangan Naik. Dengarkan saja; jangan menjawab.",
              input_audio_transcription: {
                model: "gpt-4o-transcribe",
                language: "id", // <-- Indonesian
              },
              turn_detection: { type: "server_vad" },
            },
          }),
        );
      };

      dc.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        // The user's own speech transcript completes on this event.
        if (
          msg.type ===
          "conversation.item.input_audio_transcription.completed"
        ) {
          console.log("[transcript]", msg.transcript);
          setTranscript((prev) => (prev ? prev + " " : "") + msg.transcript);
        }
        // Incremental deltas (optional live display).
        if (
          msg.type === "conversation.item.input_audio_transcription.delta"
        ) {
          console.log("[delta]", msg.delta);
        }
        if (msg.type === "error") {
          console.error("[realtime error]", msg.error);
        }
      };

      // 5. SDP offer -> POST to /v1/realtime/calls -> apply answer.
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      setStatus("negotiating");
      const sdpRes = await fetch(
        `https://api.openai.com/v1/realtime/calls?model=${REALTIME_MODEL}`,
        {
          method: "POST",
          body: offer.sdp,
          headers: {
            Authorization: `Bearer ${EPHEMERAL}`,
            "Content-Type": "application/sdp",
          },
        },
      );
      const answer = { type: "answer" as const, sdp: await sdpRes.text() };
      await pc.setRemoteDescription(answer);
    } catch (err) {
      console.error(err);
      setStatus(`error: ${(err as Error).message}`);
    }
  }

  function stop() {
    // Clean close: data channel, tracks, peer connection, then null refs.
    dcRef.current?.close();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    pcRef.current?.close();
    dcRef.current = null;
    streamRef.current = null;
    pcRef.current = null;
    setStatus("closed");
  }

  return (
    <div style={{ padding: 40, fontFamily: "monospace", color: "#e2ebe6" }}>
      <h1>Realtime voice spike</h1>
      <p>status: {status}</p>
      <button onClick={start} style={{ marginRight: 8 }}>
        start
      </button>
      <button onClick={stop}>stop</button>
      <h3>transcript</h3>
      <pre style={{ whiteSpace: "pre-wrap" }}>{transcript || "—"}</pre>
    </div>
  );
}
