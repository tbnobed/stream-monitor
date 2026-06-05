---
name: FastAPI collection-route trailing slash 307
description: Why collection routes must be registered with "" not "/", and a uvicorn --reload shutdown gotcha that masks the fix
---

# FastAPI collection routes: register with "" not "/"

Collection endpoints under a prefixed router (e.g. `APIRouter(prefix="/devices")`) must be
declared as `@router.get("")` / `@router.post("")` / `@router.patch("")`, **not** `("/")`.

**Why:** `("/")` makes the canonical path `/api/devices/` (trailing slash). The OpenAPI spec and
the generated React client call the no-slash form `/api/devices`. FastAPI answers the no-slash
request with a `307 Temporary Redirect` to add the slash. Browsers/fetch usually replay GET through
a 307 transparently (so list views appear to work), but POST/PATCH/DELETE replays fail behind the
self-hosted nginx/TLS reverse proxy (`vdi.obtv.io`) — the mutation just loops on repeated 307s and
the user sees "can't create / can't save".

**How to apply:** Any new collection route (the bare `/{prefix}` path) gets `""`. Item-level routes
(`/{id}`, `/{id}/...`) are unaffected. Intentional dual-slash routes like proxy `/whep` + `/whep/`
are the rare exception — leave those alone. After changing routes, audit every router, not just the
one the user reported: settings PATCH and guacamole were missed on the first pass.

## uvicorn --reload gotcha that hides the fix

`uvicorn --reload` does a *graceful* shutdown that waits for open connections to close. This app's
SSE endpoint (`/api/stream/status`) is held open by nginx with `proxy_read_timeout 24h`, so the
reloader gets stuck in "Waiting for connections to close" and the new code never starts — the
backend stops accepting connections and curl returns `000`.

**How to apply:** After editing backend code, don't trust the auto-reload when SSE clients are
connected. Do a hard `restart_workflow` on "artifacts/api-server: API Server" and only then verify.
