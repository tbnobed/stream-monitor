---
name: QR phone-remote token model
description: How the public, no-login phone remote authorizes and why it bypasses the auth gate
---

The desktop remote panel can mint a one-time URL (`/m/<token>`) shown as a QR; scanning opens a touch remote that controls ONE device with no login.

Authority model (do not "fix" by adding session auth):
- The token IS the authority: a 256-bit `secrets.token_urlsafe(32)`, bound to a single device, in-memory store with a 90s TTL (`services/remote/mobile_tokens.py`). The desktop heartbeats every 30s to extend it while the panel is open.
- `routers/mobile_remote.py` is intentionally the ONLY router included WITHOUT `get_current_user`. Minting + heartbeat are on the auth'd `/devices/{id}/remote/mobile-token*` routes. Unknown/expired token → 404 everywhere.
- Frontend: `App.tsx` must keep `/m/:token` OUTSIDE `AuthProvider`/`AuthGate`, else the phone hits the login wall.

**Why:** phones aren't logged in; a short-lived single-device bearer token is the whole point. Session/cookie auth would defeat it.

**How to apply:** when touching auth/router wiring, preserve the public router's no-auth inclusion and the outside-the-gate route. Lifecycle leak to watch: if the QR panel closes before `createMobileToken` resolves, revoke the late-arriving token client-side (already handled in RemoteControl.tsx) so it doesn't linger until TTL.
