---
name: HLS preview plays directly (not proxied)
description: Why the HLS eyeball preview loads the master URL directly in the browser instead of going through /api/proxy like WHEP/SRS
---

# HLS preview bypasses the proxy on purpose

The monitoring-wall HLS preview uses hls.js pointed straight at `stream.master_url`,
**not** through `/api/proxy/*`.

**Why:** The "proxy everything" rule exists to avoid HTTPS mixed-content and CORS for
HTTP-only upstreams (SRS WHEP/API are plain HTTP). The customer's HLS origins are HTTPS
and return `access-control-allow-origin: *`, so the browser can fetch manifest + segments
directly. A full HLS proxy would have to rewrite every manifest (segment + key URLs)
recursively — large effort for no benefit here.

**How to apply:** If someone adds an HTTP-only or non-CORS HLS source, the in-browser
preview will fail (the server-side health worker still works, since it fetches manifests
itself). At that point build a manifest-rewriting proxy or restrict previews to HTTPS+CORS
origins. Don't assume the preview failing means the stream is down — check CORS/scheme first.
