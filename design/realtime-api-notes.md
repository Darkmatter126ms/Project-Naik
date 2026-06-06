# Realtime API — Connection Pattern, Quirks & Demo-Day Fallback

Canonical reference for Naik's 90-second voice intake. Consolidates Hilda's
research (`api/realtime-api-notes.md`) with the as-built code and the day-5
contingency procedure. **If voice and this doc disagree, the code wins** — the
authoritative implementations are:

| File | Role |
|---|---|
| `api/realtime.py` | Flask `POST /realtime/token` — mints the ephemeral token. |
| `web/lib/useRealtimeVoice.ts` | The WebRTC hook (connect, transcribe, 90s cap, clean close). |
| `web/app/intake/page.tsx` | Consumes the hook; cached-audio + manual fallback. |
| `web/public/audio/*.mp3` | 3 cached intakes (Sari, Budi, Aisyah). |
| `web/scratch/voice-test.tsx` | Throwaway spike — not imported by the app. |

## Test status (read this first)

- ✅ **Cached-audio path: verified locally.** This is the demo's safety net and
  it works without any OpenAI key (see below). The intake page reaches `/results`
  with a correct `FinalResponse` from cached input.
- ⚠️ **Live WebRTC path: implemented but not yet end-to-end tested.** It needs
  `OPENAI_API_KEY` on the Render backend and a real mic; that test is pending.
  Treat live voice as **High risk** (per the risk register) and assume it may not
  work at Suntec. The demo does **not** depend on it.

## Connection shape (GA WebRTC interface)

The browser is a WebRTC peer to OpenAI, authenticated by a short-lived
**ephemeral token**. The real `OPENAI_API_KEY` never reaches the browser. As
implemented in `useRealtimeVoice.ts`:

1. Browser `POST ${API_BASE}/realtime/token` → Flask. `API_BASE` defaults to
   `http://localhost:5050`; set `NEXT_PUBLIC_API_BASE_URL` to the Render URL for
   the deployed demo.
2. Flask `POST https://api.openai.com/v1/realtime/client_secrets` with the real
   key → `{ client_secret: { value, expires_at } }`. The session config (model
   `gpt-realtime`, Indonesian transcription, server VAD) is baked into the token.
3. Browser: `getUserMedia({audio:true})` → `RTCPeerConnection` → add mic track →
   data channel `oai-events` → `createOffer` / `setLocalDescription`.
4. Browser `POST https://api.openai.com/v1/realtime/calls?model=gpt-realtime`
   with `Content-Type: application/sdp`, body = offer SDP,
   `Authorization: Bearer <ephemeral>` → answer SDP → `setRemoteDescription`.
5. Data channel opens → `session.update` sent → user-speech transcripts stream
   in as `conversation.item.input_audio_transcription.completed`.

### Quirk — GA endpoint names changed

It is **`/v1/realtime/client_secrets`** (mint) and **`/v1/realtime/calls`**
(SDP). The pre-GA paths `/v1/realtime/sessions` and `/v1/realtime` return 404.
Most online tutorials still show the old paths.

### Quirk — set Indonesian in *two* places

Language is pinned both in the minted token (`api/realtime.py`:
`audio.input.transcription = {model: "gpt-4o-transcribe", language: "id"}`) and
again in the client `session.update` on data-channel open. Pinning `id` improves
word-error-rate over auto-detect; the cost is that English code-switching mid-
sentence degrades — acceptable for a Bahasa-first intake.

### Quirk — listen-only session

Naik only needs the user's transcript, not a spoken reply. The session
instructions tell the model not to respond
(`"...jangan menjawab."`) and `turn_detection: server_vad` segments utterances.
We accumulate `.completed` transcripts into one string; the model never speaks.

### Quirk — ephemeral token is short-lived

Mint immediately before connecting; never cache it. It is only valid to *start*
a session (≈1 minute). The session's own max duration is far longer than our
90-second cap, so **our client-side 90s `setInterval` is the controlling limit**,
not OpenAI's — on reaching 0 the hook calls `stop()`.

### Clean close

`cleanup()` (also returned from a `useEffect`, so navigation tears down the
session): clear timer → `dataChannel.close()` → stop every mic track
(`getTracks().forEach(t => t.stop())`, which clears the browser's mic indicator)
→ `peerConnection.close()` → null all refs. No leaked mic, no dangling peer.

## Fallback-to-cached procedure (demo day)

The intake page is built so **the transcript is filled regardless of audio**.
Tapping **"Use cached audio"** does two things at once (`intake/page.tsx`):
it (a) writes the persona's canonical transcript straight into the textarea, and
(b) plays the MP3 so judges hear a voice. Step (a) does not depend on step (b) —
even if audio playback fails, the transcript is present and **Analyze** is ready.
So the pipeline receives the *same text* whether the input was live or cached.

There are therefore **three input tiers**, each degrading safely into the next:

1. **Live voice** — press mic, speak/play, transcript streams in. (High risk.)
2. **Cached audio** — "Use cached audio": transcript auto-filled + MP3 plays.
   (Verified; this is the default for the demo.)
3. **Manual** — on any error the textarea stays editable; type/paste the
   transcript and hit Analyze. (Always works, no network to OpenAI needed.)

### Day-of decision rule (from the plan)

> If live voice fails in the first 10 minutes of setup, **switch to cached
> permanently and do not debug live voice during the day.**

Concretely:
- **Setup hour:** try live once. If it connects and transcribes Indonesian
  cleanly, fine. If it stalls, flips to `error`, or mis-transcribes — stop.
- **Switch:** use **"Use cached audio"** for every run thereafter. Narration
  Beat 1 already has the cover line: *"I'll use our cached intake so we stay on
  time."*
- **If even the backend is down** (e.g. Render cold-start or no key): the textarea
  is pre-fillable; paste Sari's transcript and Analyze. The orchestrator runs on
  the heuristic path without an OpenAI key, so `/results` still populates.

### Pre-demo warm-up (1 minute before)

1. Hit `${API_BASE}/health` from a cold tab → expect `db: ok` (warms Render).
2. Open `/intake`, tap **Use cached audio** for Sari once → confirm transcript
   fills and `/results` renders all four panels with the compliance badge green.
3. Leave the tab open and warm. Do not reconnect live voice after this.

## Env / config checklist

- `OPENAI_API_KEY` — Render backend only (enables `/realtime/token`; without it
  the endpoint returns 503 and the UI drops to cached/manual).
- `NEXT_PUBLIC_API_BASE_URL` — Vercel; point at the Render backend (otherwise the
  hook calls `localhost:5050` and the token fetch fails in production).
- `NAIK_REALTIME_MODEL` — defaults to `gpt-realtime`. Use `gpt-realtime-mini`
  during testing to save cost; switch back for the demo.
- Confirm the mic-permission prompt behaves on the **demo laptop's** browser
  before the day — a denied prompt routes to `onError` → manual fallback, which
  is fine, but better to know in advance.

## Open items

- Run the live WebRTC path once with the key on Render and record the actual
  result here (replace the ⚠️ above with a ✅ or a documented failure mode).
- Spot-check that each cached MP3's audio matches its canonical transcript text
  (the pipeline only consumes the text, but judges hear the audio).
