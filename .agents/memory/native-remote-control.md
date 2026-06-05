---
name: Native OTT remote control
description: Non-obvious constraints of the services/remote driver layer (pairing state, platform mapping, optional deps)
---

# Native OTT remote control

Backend talks directly to each device's LAN IP via its native protocol. Devices + app server must share one private LAN (no bridge agent).

## Constraints that aren't obvious from the code

- **Pairing sessions are in-memory only.** Apple TV (Companion PIN) and Google TV (androidtv PIN) pairing flows hold a session object in a module-level dict between `pair/begin` and `pair/finish`. A backend restart between those two calls loses the session and the user must restart pairing. Persisted credentials (post-finish) live in `Device.remote_config` and survive restarts.
  **Why:** the pairing handshake objects from pyatv/androidtvremote2 are live network sessions, not serializable state.

- **`chromecast` platform == Google TV**, controlled via `androidtvremote2`. Legacy Chromecast dongles (cast-only, no D-pad) are NOT controllable this way. If a user has an old cast dongle, native remote will not work — only Google TV / Chromecast-with-Google-TV devices respond.

- **Drivers lazy-import their optional libs inside methods**, never at module top. This is deliberate: a missing/broken optional dep (pyatv, pychromecast, androidtvremote2, adb-shell) must disable only that one platform and return a clean error, never crash API startup. Keep new drivers following this pattern.

- **Roku (ECP) needs no pairing** — just the IP. Fire TV (ADB) pairing = accept the on-TV "allow debugging" prompt (no PIN). Apple TV / Google TV require a PIN shown on the TV.
