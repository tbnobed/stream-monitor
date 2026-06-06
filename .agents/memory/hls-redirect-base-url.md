---
name: HLS health-check redirect base URL
description: Why the HLS worker must resolve relative playlist/segment/key URIs against the FINAL (post-redirect) URL, not the configured master_url
---

# HLS health-check redirect base URL

Relative URIs in an HLS manifest (rendition playlists, segments, `#EXT-X-KEY` URIs)
must be resolved against the **final URL after following redirects**, never against
the originally configured `master_url`.

**Why:** Some CDNs (notably JWPlayer: `cdn.jwplayer.com/live/broadcast/<id>.m3u8`)
302-redirect the master to a *different host* (e.g.
`livecdn.use1-0004.jwplive.com/.../live.isml/.m3u8`). The manifest then lists
relative renditions like `live-video=600000.m3u8`. Resolving those against the
original host yields a 404 → the worker marks a perfectly healthy stream **DOWN**.
The browser (hls.js) resolves against the final URL, so playback works fine — which
is the tell: tile plays video but backend says DOWN.

**How to apply:** In `workers/hls_worker.py`, `check_manifest` returns
`final_url = str(resp.url)`; the variant fetch resolves against that (and returns
its own `str(resp.url)` as the segment base); segment/ffprobe/key resolution all use
`urllib.parse.urljoin(base, uri)` (not f-string concatenation — urljoin also handles
absolute-path `/seg.ts` URIs). Any new relative-URI resolution in this worker must
follow the same final-URL + urljoin pattern.
