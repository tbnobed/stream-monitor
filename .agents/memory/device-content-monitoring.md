---
name: Device content monitoring (black/freeze/silence)
description: Device health is two-layer (WHEP feed-loads + ffmpeg content analysis); RTMP is blocked in Replit dev.
---

# Device health is two layers, not one

A device tile is HEALTHY only if BOTH are true:
1. **Feed loads** — `probe_whep` confirms decoded WebRTC frames arrive (SRS 201s even for dead streams, so frames are the only real signal).
2. **Program alive** — `analyze_device_content` pulls the device's RTMP ingest and runs ffmpeg `blackdetect`/`freezedetect`/`silencedetect`. Black/frozen → DOWN, silence → WARNING.

**Why:** "WebRTC stream loads for the app" ≠ "the right content is playing." A device stuck on a black/frozen/silent program still delivers frames and used to read HEALTHY. The blackdetect/freezedetect/silencedetect thresholds existed in Settings but were never wired to the device worker until this work.

**How to apply:** Each detect filter only emits its marker (`black_start`/`freeze_start`/`silence_start`) when its *duration* threshold is exceeded, so presence of the substring = a sustained fault. Detection is fail-OPEN: any ffmpeg/pull error returns `analyzed:False` and must never flip a loading stream to DOWN.

# RTMP (port 1935) is blocked in the Replit dev sandbox

ffmpeg pulling `rtmp://cdn1.obedtv.live:1935/live/<key>` hangs/timeouts in the Replit dev environment — outbound 1935 is firewalled. WHEP works in dev because it's plain HTTP on port 2023. The content-analysis layer therefore only does real work on the user's LAN Docker deploy (which can reach the ingest); in dev it silently fails open.

**How to verify detection logic without RTMP:** point `analyze_device_content` at a local synthetic file — e.g. `ffmpeg -f lavfi -i color=c=black ... + anullsrc` (flags black+freeze+silence) vs `testsrc2 + sine` (clean). Confirms the filter chain + substring parsing independent of network reachability.
