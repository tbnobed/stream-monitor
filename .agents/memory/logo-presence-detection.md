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

**The region MUST be tight around the logo — this is the #1 cause of false "logo not detected".** NCC compares the *whole* region crop (resized to 48×48), so a box much larger than the logo is dominated by the changing picture around it. The crucial subtlety: the false DOWN is a *cross-time* effect — the saved template is compared against a LATER frame whose program content differs, so the scene part of a loose box decorrelates. Two frames close in time can pass while saved-ref-vs-now fails. **Empirically proven (vodfire/TBN, 1920×1080):** loose box {x:.7,y:.03,w:.27,h:.16} saved-ref vs a later different program ≈ 0.15 (→ false DOWN); the TIGHT box {x:0.847,y:0.042,w:0.075,h:0.051} hugging just the logo scored ~1.0 across the same 14s scene change. So always validate a candidate region by NCC of one batch's crop vs a *later* batch's crop (different scene), not two adjacent frames. **How to apply:** capture endpoint returns a live `match_score`; UI surfaces it on Preview so operators shrink the box until score ≫ threshold, then re-capture. Treat a low score as setup/tuning, not a matching-code bug.

**Temporal-stability auto-tighten does NOT work reliably.** Tried locating the logo inside a loose box via per-pixel temporal std across a capture burst (logo = stable, scene = moving). Fails when the scene is low-motion during capture (observed median temporal std 0.9 over 6s) — the whole box reads as stable and nothing separates logo from background. Don't ship auto-tighten; rely on a tight default + operator tuning with the live score.

**Sliding-window matcher (`services/logo.py: match_score`) for drift tolerance.** Detection and the live `match_score` both scan the template at ±25% offsets of the box (9 positions) and take the best NCC, so a slightly-misaligned box still locks on. This tolerates drift but does NOT fix loose-box scene dilution — only a tight box does. Default region was shrunk to a small top-right box (x:85%, y:4%, w:9%, h:6%) so new devices start near a typical channel bug. Device-current-status lives on `Device.current_status`; per-check logo metrics live under `check_results.detail["content"]` (logo_judged/logo_score/logo_match_ratio/logo_present/logo_missing), NOT at detail top level.

**How to apply:** new live-picture checks → add to the `probe_whep` tally + `_content_verdict`, gate behind a per-device enable flag, and require the ≥3-frame / ≥85% sustained guard before emitting a negative verdict.
