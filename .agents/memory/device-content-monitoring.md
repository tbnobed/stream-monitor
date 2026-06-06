---
name: Device content monitoring (black/freeze/silence)
description: Device health is two-layer (WHEP feed-loads + decoded-WebRTC-frame content analysis). No RTMP/ffmpeg.
---

# Device health is two layers, not one

A device tile is HEALTHY only if BOTH are true:
1. **Feed loads** — `probe_whep` confirms decoded WebRTC frames arrive (SRS 201s even for dead streams, so frames are the only real signal).
2. **Program alive** — the SAME `probe_whep` pass inspects the already-decoded frames with numpy: per-frame mean luminance → black, mean abs diff between consecutive frames → freeze, audio RMS→dBFS → silence. Black/frozen → DOWN; audio-but-no-video → WARNING; silence → WARNING.

**Why:** "WebRTC stream loads for the app" ≠ "the right content is playing." A device stuck on a black/frozen/silent program still delivers frames and used to read HEALTHY.

**How to apply:** Detection is fail-OPEN — a verdict is positive only when ≥3 frames judged AND bad fraction ≥85% (`CONTENT_MIN_FRAMES`/`CONTENT_BAD_RATIO`); any frame-decode error is swallowed. Black is checked before freeze (a black frame is also frozen). Settings thresholds are reinterpreted for per-frame analysis: `blackdetect_threshold`×255 = black luma cutoff, `freezedetect_noise`×255 = freeze diff cutoff, `silencedetect_noise` parsed as dBFS.

# Analyse decoded WHEP frames, NOT RTMP — works in dev AND on LAN

**Why:** RTMP (port 1935) is firewalled in the Replit dev sandbox, so the original ffmpeg-on-RTMP content analysis always timed out and failed open → a black tile stayed HEALTHY in dev. WHEP is plain HTTP on 2023 and reachable everywhere. The frames aiortc already decodes in `probe_whep` are the exact picture the operator sees, so analysing them needs no second connection and no RTMP reachability.

**How to apply:** When content analysis is on, `probe_whep` must sample the FULL `device_content_sample_seconds` window and NOT break early on the frame threshold — audio reaches the threshold in <1s and would otherwise leave ~0 video frames (the original bug: `video_frames` logged as 0 while audio flowed). `av.VideoFrame.to_ndarray(format="gray")` and `AudioFrame.to_ndarray()` both require numpy (added to requirements.txt). Verify against a live black stream directly: `await probe_whep(base,'live',key,content={...})` and read `detail["content"]`.
