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

## `no_video` must be gated on RTP, not decoded-frame count
**Do NOT treat "0 decoded video frames" as proof of no picture.** aiortc's *software* H264 decoder can decode zero frames for a stream the browser plays perfectly — a keyframe (IDR) lands outside the short, contended sample window while multiple probes decode concurrently, so the worker sees `video_judged==0` while audio flows → false "No video frames" WARNING. Observed: one device consistently decoded 0 frames in the 4-way-concurrent worker but 270+ frames when probed standalone with a longer window.

**Fix:** after sampling, read the receiver's `inbound-rtp` video `packetsReceived` via `pc.getStats()` (aiortc exposes `packetsReceived`, `packetsLost`, `jitter`, `ssrc`, `kind`, `type` — **no `bytesReceived`**). `no_video` fires only when decoded frames are 0 AND RTP is essentially absent (`< MIN_VIDEO_RTP_PACKETS`, 10). RTP present + 0 decoded → fail open, stamp `content.video_undecoded`.

**Why:** the operator's player is what matters; our backend decoder being slow/contended is not a stream fault. **How to apply:** any "we couldn't decode it" signal must be distinguished from "it isn't being sent" before alerting. Also distinguish a **stats-read failure** from "zero RTP": `video_rtp_packets` is `None` (unknown) when `getStats()` itself throws, and `no_video` must fail open on `None` — only positively-observed low RTP may fire it. Defaulting an unread stat to 0 would re-introduce the exact false positive.

## Black screens get a grace period; freeze must be suppressed during it
A black screen does NOT alert DOWN immediately — many channels load a black slate for a minute or two before the show starts. A black screen only escalates to DOWN after it has been *continuously* black for `BLACK_GRACE_SECONDS` (process **env var**, default 300s/5min; read via the `config` singleton, so a container restart applies a new value — this is intentionally env/.env-controlled and passed through docker-compose, NOT a DB Setting like the logo grace). The worker stamps `Device.black_since` on the first black cycle and clears it the moment the picture returns or the feed drops.

**Critical subtlety — black implies frozen.** A black slate is also static, so the freeze verdict fires on it too. If you grace black but let freeze escalate immediately, the slate just trips "Frozen frame" and the grace is useless. **Fix:** make the `if content.get("black")` branch unconditional in the status mapping (only sets DOWN when the grace has elapsed) so the `elif content.get("freeze")` is never reached while black is true — this suppresses freeze for the whole grace window. A genuine freeze on a non-black picture (`black==False`) still alerts immediately. **Why this matters for any future "grace" on a static-picture verdict:** whatever you grace must also short-circuit the other verdicts that the same condition would trigger, or they leak through and defeat the grace.

## Known limitation
A genuinely static intentional graphic (e.g. a "We'll be right back" bumper) is pixel-identical over time and will read as frozen. Distinguishing intentional static cards from a real freeze needs more signal (audio/OCR) and is not currently attempted.
