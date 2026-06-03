# Realtime API — integration notes (Block 2, Hilda)

Findings from wiring the OpenAI Realtime API voice path for Naik's 90-second
intake. Source: OpenAI Realtime WebRTC GA docs (current as of build).

## Connection shape (GA WebRTC interface)

The browser connects directly to OpenAI as a WebRTC peer, authenticated with a
short-lived **ephemeral token**. The real `OPENAI_API_KEY` never touches the
browser. Flow:

1. Browser `POST ${API_BASE}/realtime/token` → our Flask backend.
2. Flask `POST https://api.openai.com/v1/realtime/client_secrets` with the real
   key → returns `{ client_secret: { value, expires_at } }`.
3. Browser creates an `RTCPeerConnection`, adds the mic track, creates a data
   channel (`oai-events`), makes an SDP offer.
4. Browser `POST https://api.openai.com/v1/realtime/calls?model=gpt-realtime`
   with `Content-Type: application/sdp`, body = offer SDP, `Authorization:
   Bearer <ephemeral>` → returns the answer SDP.
5. Browser applies the answer; data channel opens; transcripts stream in.

> Endpoint names changed at GA. It is **`/v1/realtime/client_secrets`** (mint)
> and **`/v1/realtime/calls`** (SDP), not the older `/v1/realtime/sessions` or
> `/v1/realtime` base seen in pre-GA tutorials. Using the old paths returns 404.

## Setting language to Indonesian

Two places, set both:

- **In the minted token** (server side, `api/realtime.py`): the session config
  includes `audio.input.transcription = { model: "gpt-4o-transcribe",
  language: "id" }`. Binding it to the token means the browser inherits it.
- **In the client `session.update`** (sent on data-channel open): repeat
  `input_audio_transcription: { model: "gpt-4o-transcribe", language: "id" }`.

Pinning `language: "id"` measurably improves word-error-rate vs leaving it to
auto-detect, at the cost of multilingual handling — fine for our Bahasa-first
intake. If Sari code-switches to English mid-sentence, accuracy on those words
drops; acceptable for the demo.

## Receiving the user's transcript

The transcript of the **user's own speech** (not the model's reply) arrives as:

- `conversation.item.input_audio_transcription.completed` → `msg.transcript`
  (final text for an utterance; we accumulate these into one string).
- `conversation.item.input_audio_transcription.delta` → `msg.delta`
  (incremental; optional, for live display).

Because Naik only needs to *listen* (not converse), the session instructions
tell the model not to respond, and `turn_detection: server_vad` lets OpenAI
segment utterances for us.

## Session timeout behaviour

- Ephemeral tokens are short-lived (≈1 minute to *start* a session). Mint right
  before connecting; do not cache.
- The Realtime session itself has a maximum duration (multiple minutes) — far
  longer than our 90-second intake, so we hit our own cap first.
- **Our cap**: `useRealtimeVoice` runs a 90s `setInterval`; on reaching 0 it
  calls `stop()`. This is the controlling limit, not OpenAI's.

## Clean close

`stop()` performs, in order: clear the timer → `dataChannel.close()` → stop all
mic tracks (`getTracks().forEach(t => t.stop())`, which releases the mic
indicator) → `peerConnection.close()` → null the refs. The hook also returns
`cleanup` from a `useEffect` so unmounting the page (navigation) tears the
session down — no leaked mic or dangling connection.

## Failure handling (demo safety)

Every failure path (`OPENAI_API_KEY` unset → 503 from our endpoint, mic
permission denied, SDP non-2xx, `error` event) routes to `onError`, which sets a
visible note and leaves the transcript textarea editable. The intake page then
works as manual entry, so a venue-wifi voice failure never hard-blocks the
demo. This matches the build-plan risk register (voice = High risk → cached /
manual fallback non-negotiable).

## What ships where

| File | Role |
|---|---|
| `web/scratch/voice-test.tsx` | Throwaway spike; not imported by the app. |
| `web/lib/useRealtimeVoice.ts` | Reusable hook used by the intake page. |
| `api/realtime.py` | Flask `/realtime/token` ephemeral minting. |
| `app/intake/page.tsx` | Consumes the hook; manual fallback on error. |

## Open items for Phase 3

- Record the 3 cached MP3 intakes (Sari + 2 alternates) and wire a "Use cached
  audio" path that feeds the same transcript pipeline — the venue-wifi
  insurance policy.
- Consider `gpt-realtime-mini` for cost during testing; switch to `gpt-realtime`
  for the demo (set `NAIK_REALTIME_MODEL`).
- Confirm mic permissions prompt behaves on the demo laptop's browser before
  the day.
