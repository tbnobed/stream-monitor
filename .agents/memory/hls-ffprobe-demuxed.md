---
name: HLS ffprobe demuxed false-DOWN
description: Why the HLS worker's ffprobe segment check must accept video-only (or audio-only) segments
---

The HLS worker's ffprobe deep check (`workers/hls_worker.py: ffprobe_segment`) must treat a segment as valid when it decodes to **at least one** media stream (`has_video OR has_audio`), NOT both.

**Why:** Demuxed HLS packagers (e.g. JWPlayer / Unified Streaming `live.isml`) expose separate audio and video renditions. The video variant's segments (`live-video=600000.ts`) are video-only; audio is a separate group playlist. Requiring `has_video AND has_audio` flagged perfectly healthy streams as DOWN ("Segment decode failed (ffprobe)") even though they played fine in the browser. Muxed streams (e.g. Xumo's `live-audio...-video....m3u8`) carry both and pass either way.

**How to apply:** If asked to make the audio check stricter, do it by fetching the audio group rendition separately — never by ANDing has_video/has_audio on a single (possibly video-only) variant segment. The worker always fetches `playlists[0]`, which on demuxed streams is the top video variant.
