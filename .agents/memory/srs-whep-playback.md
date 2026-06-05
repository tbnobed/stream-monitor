---
name: SRS WHEP playback quirks
description: Non-obvious requirements of the SRS WHEP SDK + proxy needed for WebRTC tiles to play
---

# SRS WHEP playback through the HTTPS proxy

Three non-obvious things must all be true for WebRTC device tiles to play. Each one fails silently/confusingly on its own.

## 1. The play URL must contain the substring `/whep/` (with trailing slash)
The real SRS SDK (`public/srs.sdk.js`, `SrsRtcWhipWhepAsync.play`) validates the URL synchronously:
`if (url.indexOf('/whip-play/') === -1 && url.indexOf('/whep/') === -1) throw ...`
So the player URL must be `/api/proxy/whep/?stream=...` — NOT `/api/proxy/whep?stream=...`.
**Symptom if wrong:** console logs `WHEP play error {}` but backend shows ZERO `POST /api/proxy/whep` requests — the SDK throws before any network call. The backend route must also accept the trailing slash.

## 2. The proxy must strip the `Location` response header
After a successful answer the SDK runs `new URL(location, url)` using the *play url* as the base. Our play url is relative (`/api/proxy/whep/...`), and `new URL()` rejects a relative base → `Failed to construct 'URL': Invalid base URL` thrown in `xhr.onload`, killing playback right after a valid answer.
**Fix:** strip `location` from the WHEP proxy response so the SDK skips the `if (location)` branch. (Teardown DELETE is sacrificed; fine for a always-on NOC wall — SRS times out idle sessions.)

## 3. First WHEP request often returns transient 502 (edge pull)
SRS edge-pulls the stream on the first request and returns `502 Bad Gateway` until ready, then `201 Created` on retry. The player must retry a few times with backoff before showing "Stream Disconnected", or cold starts look broken.

**Why:** all three were live simultaneously and masked each other during debugging. A 201 Created in the API Server log + `Got answer: ... msid-semantic: WMS live/<key>` in the browser console = signaling fully working.

**Note on verification:** the agent's headless screenshot browser cannot open the UDP media path to the SRS host, so tiles look black in screenshots even when signaling succeeds. Verify via the 201 + valid SDP answer in logs, not the screenshot pixels.

## Device health = actual WHEP media flow, NOT the SRS HTTP API
Two traps make the SRS HTTP API (`:1985/api/v1/streams/`) the wrong signal for "is this device's stream loading":
1. **Different server.** The SRS API node (`:1985`) and the WHEP playback edge (`:2023`) are *different SRS instances*. On-demand `vod*` streams play fine via WHEP on `:2023` but never appear in the `:1985` `/streams/` list, so a publisher-match check marks every device DOWN while video plays.
2. **201 ≠ live.** SRS answers the WHEP handshake with `201 Created` + a full valid SDP answer even for a *non-existent* stream name. The answers are byte-for-byte structurally identical to a real stream. So a 201 proves nothing about media.

The only reliable health signal is **decoded media frames actually arriving**. The device worker uses `aiortc` server-side: open a recvonly audio+video `RTCPeerConnection`, POST the offer to WHEP, and count decoded frames over a short window — HEALTHY if a few frames flow, else DOWN. The backend container CAN complete ICE/DTLS and receive RTP from the SRS host (unlike the headless screenshot browser). Audio frames arrive first/fastest; H264 video needs a keyframe so it lags — count either. Silence `aioice.ice` / `aiortc.codecs.h264` loggers (per-candidate and per-undecodable-packet spam) and hard-cap each probe with `asyncio.wait_for` so retries can't overrun the worker interval.

**Why:** the standalone WordPress wall this replaced just embedded the players; "is it loading" literally means "does the WHEP player get media." Checking the control-plane API instead produced false DOWNs on healthy streams.
