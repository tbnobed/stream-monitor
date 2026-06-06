---
name: Logo-presence detection (OTT monitor)
description: Why logo detection piggybacks on WHEP frames and how it fails open
---

# Logo-presence detection

Per-device, opt-in check that a fixed on-screen brand logo (e.g. TBN top-right) is present in the live picture; a missing logo → DOWN ("Expected logo not detected"), catching a wrong/lost channel.

**Key decision: reuse the already-decoded WHEP frames.** The device worker's `probe_whep` already decodes WebRTC frames for black/freeze/silence content analysis. Logo detection cropping + NCC runs on those same frames — NO extra connection, no RTMP. Anything that needs the live picture should hook into that single decode loop rather than opening its own stream.

**Why NCC (zero-mean normalized cross-correlation) on a 48×48 grayscale template:** robust to brightness/contrast shifts and tiny scaling, cheap per frame. Match when NCC ≥ `logo_match_threshold` (default 0.6).

**Fail-open is mandatory for any content verdict here.** `logo_missing` only fires when ≥3 frames were judged AND ≥85% lacked the logo, plus the standard 2-check debounce. Sparse/partial loads must never flip a stream to DOWN. Same rule already governs black/freeze/silence.

**Why the template is never serialized:** `logo_template` is internal base64 on the Device; the API exposes only a computed `logo_reference_set` bool. Treat captured reference imagery as internal.

**How to apply:** new live-picture checks → add to the `probe_whep` tally + `_content_verdict`, gate behind a per-device enable flag, and require the ≥3-frame / ≥85% sustained guard before emitting a negative verdict.
