---
name: Device content monitoring (black/freeze/silence on WHEP frames)
description: Why freeze must be time-spaced, and how the fail-open content verdict works
---

# Device content monitoring

Device health analyses the already-decoded WHEP video/audio frames in `probe_whep` (numpy, no RTMP, works in Replit dev + LAN): per-frame mean luminance → black, time-spaced mean abs diff → freeze, audio RMS→dBFS → silence. Verdicts map: black/freeze → DOWN, no-video/silence → WARNING.

## Freeze must be compared over TIME, not frame-to-frame
**Do NOT compare immediately-consecutive decoded frames for freeze.** At full frame rate (~25fps), a low-motion live shot (locked-off camera on a speaker, talking head) has tiny per-frame change, so ≥85% of consecutive pairs fall under the diff threshold and a perfectly live stream reads as "frozen" → false DOWN.

**Fix:** compare each frame against a reference grabbed ≥`FREEZE_INTERVAL_SECONDS` (1.0s) earlier. Over a second, real content (even slow) accumulates clear change; a true freeze stays ~0 even seconds apart. This is the durable rule — any future "stillness" check needs a time baseline, not adjacent frames.

**Why:** users reported alert sensitivity "way too high"; the root cause was the frame-adjacency comparison, not the threshold value.

## Fail-open rules (shared by all content verdicts)
A negative verdict only fires when ≥`CONTENT_MIN_FRAMES` (3) samples were judged AND the bad fraction is sustained (≥`CONTENT_BAD_RATIO`, 0.85), plus the standard 2-check incident debounce. Any frame-decode error is swallowed — analysis must never cause a false DOWN. Apply the same guard to any new live-picture check (e.g. logo presence).

## Known limitation
A genuinely static intentional graphic (e.g. a "We'll be right back" bumper) is pixel-identical over time and will read as frozen. Distinguishing intentional static cards from a real freeze needs more signal (audio/OCR) and is not currently attempted.
