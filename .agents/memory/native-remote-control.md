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

## Keep the remote-render critical path network-free
The `/capabilities` endpoint must stay a pure no-network call (protocol + key list).
It previously called `list_apps()`, which on Apple TV (pyatv Companion) opens a full
device connection and enumerates installed apps — minutes-slow. The frontend gates the
entire D-pad on the capabilities query, so any network call there blocks the whole remote
from appearing. **Why:** an operator reported the remote taking ~4 min to show up even
though pairing/stream were fine. **How to apply:** never put device I/O (connect, scan,
list_apps) in `status`/`capabilities`; keep it to the actual key/launch actions. Apple TV
warm-connection reuse only helps the action path, not render.

## Pairing-based drivers must reuse a warm connection
Apple TV (pyatv Companion) and Chromecast/Google TV (androidtvremote2) both establish
an expensive session per action — a Companion handshake / TLS handshake. Reconnecting on
every key press is the latency culprit (seconds per press). Both libraries are designed to
hold a long-lived connection. **Pattern:** cache the live connection in a module-level dict
keyed by device.id, guard with a per-device asyncio.Lock, keep it warm with an idle reaper
(`loop.call_later` -> coroutine that re-acquires the lock + rechecks last_used before
closing), reconnect-once on a failed op, prime it from `status()`, and drop it on re-pair.
Roku (ECP, plain HTTP) is stateless and does NOT need this. Fire TV (ADB) DOES — its connect does an RSA auth handshake, but note ADB connect/close are async, so connection teardown must run under the per-device lock (sync disconnect like Google TV is safe unlocked).
