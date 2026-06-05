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
