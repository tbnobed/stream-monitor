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

**Grace period for ad breaks (decision):** a per-check `logo_missing` must NOT immediately flip DOWN — ads legitimately hide the channel logo for minutes. The worker stamps `Device.logo_missing_since` on the first missing cycle and only escalates after the logo is *continuously* missing past `logo_missing_grace_seconds` (global Setting, default 300=5min). **Why:** without it, every ad break = false "wrong channel" DOWN. **How to apply:** clear the timestamp on ANY non-missing cycle (logo present, feed down, check off, sparse <3-frame samples) so each fresh disappearance gets a full grace window; the timer is internal (never serialized).

**The region MUST be tight around the logo — this is the #1 cause of false "logo not detected".** NCC compares the *whole* region crop (resized to 48×48), so a box much larger than the logo is dominated by the changing picture around it: a clearly-present logo then scores ~0.15–0.3, below a 0.6 threshold → persistent `logo_missing` → false DOWN. A tight box scores 0.8+. **Why:** observed a TBN logo plainly visible in both the saved template and the live crop, yet `logo_match_ratio` was 0.0 across 130+ judged frames purely because the default region (27%×16% of frame) swallowed scene content. **How to apply:** the capture endpoint returns a live `match_score` (NCC of the current crop vs the already-saved reference, computed before overwrite); the UI surfaces it on Preview so operators shrink the box + set threshold below it. Treat a low score as a setup/tuning problem, not a matching-code bug.

**How to apply:** new live-picture checks → add to the `probe_whep` tally + `_content_verdict`, gate behind a per-device enable flag, and require the ≥3-frame / ≥85% sustained guard before emitting a negative verdict.
