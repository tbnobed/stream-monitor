# OTT Stream Monitor

A full-stack broadcast NOC (Network Operations Center) tool that monitors live OTT device streams (Roku, Fire TV, Chromecast, Apple TV) via WebRTC and HLS source streams, with native on-screen remote control of each device. Replaces a WordPress monitoring wall.

## Run & Operate

- **Frontend**: automatically served at `/` via the `artifacts/ott-monitor: web` workflow
- **Backend**: automatically served at `/api` via the `artifacts/api-server: API Server` workflow
- Backend logs: check the "API Server" workflow console

## Stack

- **Frontend**: React + Vite, TypeScript, Tailwind CSS, TanStack Query, wouter
- **Backend**: Python FastAPI, SQLAlchemy ORM, Alembic (schema auto-created on startup)
- **DB**: PostgreSQL (Replit managed)
- **WebRTC**: SRS official WHEP SDK (`/public/srs.sdk.js`)
- **HLS**: hls.js for optional eyeball view
- **Real-time**: Server-Sent Events (SSE) at `/api/stream/status`

## Where things live

- `artifacts/ott-monitor/src/` — React frontend (pages, components, hooks)
- `artifacts/api-server/backend/` — Python FastAPI app
  - `main.py` — app entrypoint, startup (DB init, seeding, background workers)
  - `models.py` — SQLAlchemy models (devices, hls_streams, check_results, incidents, settings)
  - `schemas.py` — Pydantic request/response schemas
  - `routers/` — API route handlers (devices, hls_streams, incidents, settings, dashboard, proxy, sse, remote)
  - `services/remote/` — Native remote drivers (roku/ECP, firetv/ADB, appletv/Companion, chromecast/Google-TV androidtv) + `get_driver` factory
  - `workers/device_worker.py` — Device health loop (SRS API + ffmpeg)
  - `workers/hls_worker.py` — HLS health loop (manifest, rendition, segment, ffprobe, DRM)
  - `services/incident_service.py` — Shared debounce + incident open/close logic
  - `services/alert_service.py` — Slack/Discord/generic webhook + SendGrid email alerting
  - `requirements.txt` — Python dependencies
- `lib/api-spec/openapi.yaml` — OpenAPI contract (source of truth)
- `lib/api-client-react/` — Generated React Query hooks (from codegen)

## Architecture decisions

- **HTTPS mixed-content proxy**: All HTTP upstreams (SRS WHEP, SRS API) are proxied through `/api/proxy/*` so the browser only ever talks HTTPS to our origin. Never hardcode upstream URLs in frontend.
- **Native remote control**: The backend talks directly to each device's LAN IP using its native protocol (Roku ECP, Fire TV ADB, Google TV/Chromecast androidtv, Apple TV Companion). Devices and the app server must share one private LAN. Drivers live in `services/remote/` and use lazy imports so a missing optional library disables only that platform — it never crashes startup. Sensitive pairing creds live in `Device.remote_config` (JSON) and are never exposed in API responses; only `ip_address` and computed `remote_*` flags are returned.
- **Data-driven**: Every device, HLS stream, endpoint URL, and webhook is in PostgreSQL. Operators use the UI — never source code — to add/change items.
- **Debounce**: Status only changes officially after 2 consecutive checks agree (kills flapping). Configurable in Settings.
- **Worker isolation**: Device and HLS workers run as independent async background tasks sharing one DB, incident service, SSE feed, and alerting pipeline.
- **SSE + polling dual-mode**: The monitoring wall uses SSE for instant badge updates and 15s React Query polling as a reliability fallback.
- **ffmpeg concurrency limit**: Max 4 concurrent ffmpeg/ffprobe processes (configurable) to avoid resource exhaustion.

## Product

- **Monitoring Wall** (`/`): Dense dark grid of device tiles with live WebRTC video, status badges (HEALTHY/WARNING/DOWN/UNKNOWN), bitrate info, and a hover-to-reveal native remote control (D-pad, transport, volume, app shortcuts) per tile.
- **Phone remote (QR)**: The desktop remote panel has a "Control from phone" button that shows a QR code encoding a one-time, single-device token URL (`/m/<token>`). Scanning opens a touch-friendly remote (`pages/MobileRemote.tsx`) that controls only that device, with no login. The token is short-lived (90s TTL, extended by a 30s heartbeat from the desktop) and is revoked when the desktop remote panel closes (explicit revoke + `pagehide` beacon, with the TTL as a backstop).
- **Source Streams** (tab on wall): HLS health cards for source stream monitoring.
- **Device Registry** (`/devices`): Full CRUD for OTT devices (Roku, Fire TV, Chromecast, Apple TV, other).
- **HLS Stream Registry** (`/hls-streams`): Full CRUD for HLS source streams.
- **Incidents** (`/incidents`): Global incident feed with filtering, acknowledge, and per-item uptime %/MTTR.
- **Settings** (`/settings`, admin only): All endpoints, intervals, thresholds, and webhook URLs — editable via UI.
- **Users** (`/users`, admin only): Manage local accounts and roles.

## Authentication

The entire app (frontend + API) is gated. Unauthenticated API calls return 401; the React app shows a login screen until a session exists.

- **Two roles**: `admin` (manage users + edit settings) and `operator` (view + control devices). Settings PATCH and all `/api/users` routes require admin.
- **Local accounts**: username/password, bcrypt-hashed. On first boot, when the user table is empty, an initial admin is created from `INITIAL_ADMIN_USERNAME` (default `admin`) and `INITIAL_ADMIN_PASSWORD`. If `INITIAL_ADMIN_PASSWORD` is unset, the API generates a random one-time password and logs it once on startup (`docker compose logs api`) — no guessable `admin`/`admin` default. The `deploy/install.sh` installer also writes a random `INITIAL_ADMIN_PASSWORD` into `deploy/.env` and prints it. Change it after first login.
- **Email on accounts**: every account has an optional, format-validated email (`UserCreate`/`UserUpdate` use Pydantic `EmailStr`, backed by `email-validator`) intended for notifications (per-account email; note that SendGrid alert recipients are configured separately in Settings via `alert_email_recipients`). Admins set/edit it on the Users page; SSO stores the IdP email only when the token's `email_verified` is true.
- **Optional Authentik (OIDC) SSO**: enabled only when `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `OIDC_DISCOVERY_URL` are all set. The login page then shows a "Sign in with {OIDC_DISPLAY_NAME}" button. SSO users are auto-provisioned as `operator`. OIDC is implemented directly with `httpx` (Authlib is blocked by the package firewall): the flow does state-CSRF in the session, then code → token (`client_secret_post`) → userinfo. Behind a reverse proxy, set `OIDC_REDIRECT_URI` to the public callback URL.
- **Sessions**: signed cookies via Starlette `SessionMiddleware` (`SESSION_SECRET`). `same_site=lax`; set `SESSION_COOKIE_SECURE=true` only when served over HTTPS. Frontend is same-origin, so cookies are sent automatically — never set an auth token getter on the API client.
- **Backend layout**: `auth.py` (hashing, `get_current_user`, `require_admin`), `routers/auth.py` (`/config`, `/login`, `/logout`, `/me`, `/sso/login`, `/sso/callback`), `routers/users.py` (admin CRUD with last-admin guards). `config.py` reads `SESSION_*`, `OIDC_*`, `INITIAL_ADMIN_*`.
- **Public phone-remote endpoints (token auth, NOT session)**: `routers/mobile_remote.py` is the one router included WITHOUT the `get_current_user` dependency. Its routes under `/m/{token}` (GET session, POST `/key`, POST `/revoke`) authorize purely on the bearer token, which is a 256-bit `secrets.token_urlsafe` value bound to a single device with a 90s TTL (`services/remote/mobile_tokens.py`, in-memory — single uvicorn process, like the pairing-session store). Minting and heartbeat live on the auth'd `/devices/{id}/remote/mobile-token*` routes in `routers/remote.py`. Unknown/expired tokens always 404. On the frontend, `App.tsx` routes `/m/:token` OUTSIDE `AuthProvider`/`AuthGate` so the phone page never hits the login wall.
- **Frontend layout**: `hooks/use-auth.tsx` (provider over `useGetCurrentUser`), `pages/Login.tsx`, `pages/Users.tsx`. `App.tsx` gates routes (Settings/Users admin-only) and re-checks the current user when any query returns 401 (session expiry → back to login).

## Adding a device

Go to `/devices` → "Add Device". Fill in name, platform, and SRS stream key. The wall renders from DB — no code changes needed.

## Adding an HLS stream

Go to `/hls-streams` → "Add Stream". Enter name and master `.m3u8` URL. Health checks start automatically.

## Configuring alerts

Go to `/settings`. Paste Slack/Discord/generic webhook URLs. Toggle `alerts_enabled` and `alert_on_warning`. Save.

**Email (SendGrid)**: email alerts fire on the same incident open/resolve events. Enable by setting `SENDGRID_API_KEY` and a verified sender `ALERT_FROM_EMAIL` (env vars — in `deploy/.env` for the self-hosted deploy; optionally `ALERT_FROM_NAME`). Then set recipients in `/settings` → `alert_email_recipients` (comma-separated). Email is skipped unless the key, sender, and at least one recipient are all present. Implemented with `httpx` directly against the SendGrid v3 API (`services/alert_service.py: _send_email_alert`), no SDK.

## How SRS WHEP playback works

1. Browser initiates WebRTC via `SrsRtcWhipWhepAsync` pointing at `/api/proxy/whep?stream={key}`
2. FastAPI forwards the SDP offer to the real SRS WHEP endpoint (`http://cdn1.obedtv.live:2023/rtc/v1/whep/?app=live&stream={key}`)
3. SDP answer returns through the proxy back to the browser
4. Video plays over WebRTC — always HTTPS, never mixed-content

## How HLS detection works

Every 30s (configurable): manifest fetch → rendition audit → media-sequence stall check → segment fetch → optional ffprobe decode → DRM key check. All metrics stored in `check_results.detail` JSON.

## How device detection works

Two layers, every 15s (configurable):

1. **Feed loads?** A real WHEP (WebRTC) probe opens the device's stream and confirms decoded media frames actually arrive (`probe_whep`). SRS returns 201 even for a non-existent stream, so frames flowing is the only reliable "the capture is up" signal.
2. **Program alive?** When the feed loads, the **same WHEP probe** also inspects the *already-decoded* WebRTC frames (no extra connection, no RTMP) with numpy: per-frame mean luminance for **black**, **time-spaced** mean abs diff for **freeze** (each frame is compared against a reference grabbed ≥`FREEZE_INTERVAL_SECONDS` (1.0s) earlier, NOT the immediately-preceding frame — otherwise a low-motion live shot like a locked-off camera on a speaker reads as frozen because per-frame change is tiny), and audio RMS→dBFS for **silence**. A black or frozen screen → **DOWN**; audio flowing but **no video being sent** → **WARNING** (`No video frames`); sustained silence → **WARNING**. This catches a device stuck on a black/frozen/silent program that still delivers WebRTC frames (which would otherwise read HEALTHY). Because it analyses the exact picture the operator sees over WebRTC, it works **everywhere** (Replit dev sandbox *and* LAN) — no RTMP reachability required.

Content analysis **fails open**: a verdict is only positive when ≥3 frames were judged and the bad fraction is sustained (≥85%), so sparse/odd samples never flip a loading stream; any frame-decode error is swallowed and never causes a false DOWN. It is gated by `device_content_check_enabled` and tuned via `device_content_sample_seconds` plus the existing threshold keys, reinterpreted for per-frame analysis: `blackdetect_threshold` (×255 → black luma cutoff), `freezedetect_noise` (×255 → freeze diff cutoff), `silencedetect_noise` (dBFS, e.g. `-50dB`). The probe samples the full window when content analysis is on so it gathers enough video frames to judge (audio alone would otherwise break the loop early with ~0 video frames). The old `*_duration` and `rtmp_ingest_base_url` settings are now unused.

**`no_video` is gated on real video RTP, not decoded-frame count.** aiortc's *software* H264 decoder can yield **zero decoded frames for a stream the browser plays fine** — e.g. a keyframe (IDR) landing outside the short, contended sample window while several probes decode at once. So "0 decoded video frames" alone is NOT proof of a dead picture. After sampling, the probe reads the receiver's `inbound-rtp` video `packetsReceived` via `pc.getStats()` (stored as `video_rtp_packets` in `check_results.detail`). `no_video` fires only when decoded video frames are 0 AND video RTP is essentially absent (`< MIN_VIDEO_RTP_PACKETS`, 10). When RTP is flowing but decode produced nothing, it fails open and stamps `content.video_undecoded` for transparency instead of a false WARNING.

## How logo-presence detection works

Per-device, opt-in. Catches a wrong/lost channel by verifying a fixed on-screen brand logo (e.g. TBN, top-right) is still present in the live picture.

- **Setup (operator)**: On `/devices`, edit a device → "Logo Presence Monitoring" → toggle on, set the logo's region as top-left X/Y + width/height **percentages** (defaults target a top-right logo), then "Preview region" (shows a live snapshot with the box overlaid + the crop) and "Capture & save reference". Saving grabs a live WHEP frame, stores a 48×48 grayscale template (base64, internal — never exposed via API), the region (fractions), and the match threshold on the Device, and enables the check.
- **Detection**: piggybacks on the **same WHEP frames** the content analysis already decodes (no extra connection). Each frame's region is scored against the template via zero-mean **normalized cross-correlation (NCC)** using a **drift-tolerant sliding-window match** (`services/logo.py: match_score`): the template is scanned at small positional offsets (±25% of the box in each axis, 9 positions) and the best NCC wins, so a slightly-misaligned box still locks onto the logo. A frame "has the logo" when the best NCC ≥ `logo_match_threshold` (default 0.6). The live `match_score` shown on Preview uses the same sliding matcher, so it matches what detection sees. Verdict `logo_missing` → **DOWN** ("Expected logo not detected"), ordered after black/freeze and before no-video/silence.
- **Fails open**: `logo_missing` only fires when ≥3 frames were judged AND ≥85% of them lacked the logo, so partial loads / sparse samples never cause a false DOWN. Disabled, or with no saved template/region, the check is skipped entirely.
- **Grace period (ad breaks)**: A per-check `logo_missing` verdict does NOT immediately flip the device DOWN. The worker stamps `Device.logo_missing_since` the first cycle the logo goes missing and only escalates to DOWN ("Expected logo not detected") once the logo has been **continuously** missing for `logo_missing_grace_seconds` (global Setting, default `300` = 5 min). The stamp is cleared the instant the logo is confirmed back, the feed drops, or the logo check is off — so every fresh disappearance (e.g. each ad break) gets a full grace window and a normal 2–3 min ad break never alerts. During the grace window the device stays HEALTHY (logo suppressed; other verdicts like black/freeze still apply immediately). Tune it in `/settings`.
- **Data model**: `Device.logo_check_enabled` (bool), `logo_region` (JSON `{x,y,w,h}` fractions), `logo_match_threshold` (float), `logo_template` (Text base64, internal), `logo_missing_since` (timestamptz, internal grace timer). `DeviceOut` exposes only the computed `logo_reference_set` flag, never the template or the timer.
- **Capture endpoint**: `POST /devices/{id}/logo/reference` `{region, save, threshold?}` → returns `snapshot`/`crop` data URLs (+ dims) and `match_score` (live NCC of the current region crop vs the **already-saved** reference, computed before any overwrite; `null` when no reference exists yet); when `save=true`, persists template/region/threshold and enables monitoring. Region/threshold are bounds-validated (fractions 0–1).
- **Region must be TIGHT.** NCC compares the whole region crop, so a box much larger than the logo gets swamped by the changing picture around it and the match score collapses. Empirically, a loose box ({x:.7,y:.03,w:.27,h:.16}) scores its *saved reference* vs a later, different program at only ~0.15 (false `logo_missing`/DOWN), while a tight box hugging just the logo scores ~1.0 across the same scene change. The defaults are a small top-right box (x:85%, y:4%, w:9%, h:6%) to start near a typical channel bug, and the sliding-window matcher tolerates small misalignment — but the operator must still shrink the box to the logo. The UI shows the live `match_score` on Preview after a reference is saved so the operator can confirm the score sits well above the threshold, then re-capture. A loose region is the usual cause of a false "Expected logo not detected".
- **Wall**: device tiles now show the `failure_reason` text under the video on DOWN/WARNING (so a missing-logo alert reads clearly).
- Code: `services/logo.py` (template/NCC/frame-grab), `workers/device_worker.py` (`probe_whep` logo tally + `_content_verdict` + `check_device` mapping), `routers/devices.py` (capture endpoint), frontend `pages/Devices.tsx` (`LogoMonitorSection`).

## Dependencies

- `ffmpeg` and `ffprobe` must be available on PATH for HLS deep validation (device content analysis no longer needs ffmpeg — it analyses decoded WebRTC frames with numpy)
- `numpy` — used by the device worker to analyse decoded WHEP video/audio frames (black/freeze/silence)
- `pillow` (PIL) — used by `services/logo.py` to encode snapshot/crop preview images (JPEG/PNG data URLs) and resize logo templates
- PostgreSQL (auto-provisioned by Replit)

## Self-hosted Docker deployment (Ubuntu LAN)

For native remote control to work, the backend must run on the **same LAN/subnet** as the OTT devices (devices reject control from non-private/cross-subnet source IPs). The `deploy/` directory packages the whole app to run on the user's own Ubuntu server.

- `deploy/install.sh` — one-shot Ubuntu installer: installs Docker Engine + Compose plugin, generates `deploy/.env` (random DB password) on first run, then `docker compose up -d --build`. Run with `sudo bash deploy/install.sh` from a full checkout of the repo on the server.
- `deploy/docker-compose.yml` — three services:
  - `db` — `postgres:16-alpine`, named volume `pgdata`, published only to `127.0.0.1:5432` (not exposed to LAN).
  - `api` — FastAPI backend (`deploy/api/Dockerfile`, python:3.11-slim + ffmpeg + aiortc libs). Uses `network_mode: host` so outbound traffic to devices carries the host's private LAN IP and mDNS discovery works. **Binds uvicorn to `127.0.0.1:8080`** (loopback only) so nginx is the single ingress and the API is not exposed on the LAN; device control is all outbound so this doesn't affect reachability. Connects to DB on `127.0.0.1:5432`.
  - `web` — nginx serving the built React app + reverse-proxying `/api` (`deploy/web/Dockerfile` multi-stage build; `deploy/web/nginx.conf`). Also `network_mode: host` (listens on :80, proxies to `127.0.0.1:8080`).
- `deploy/.env.example` — template; `POSTGRES_PASSWORD` must match the password inside `DATABASE_URL`.
- Production routing: nginx serves the SPA at `/` and passes `/api/*` through **unchanged** (FastAPI `root_path="/api"` accepts the prefixed path — same contract as the Replit dev proxy). SSE/WebRTC proxying uses `proxy_buffering off` + long timeouts.
- **amd64 only**: `pnpm-workspace.yaml` pins frontend platform binaries (esbuild/rollup/lightningcss/oxide) to linux-x64, so the `web` image must build on x86_64. `install.sh` warns on other architectures.
- The frontend talks to the API via relative `/api` paths (same-origin), so no build-time API URL is needed; the build only requires `BASE_PATH=/` and a dummy `PORT`.

## User preferences

_Populate as you build._

## Gotchas

- Always run codegen after changing `lib/api-spec/openapi.yaml`: `pnpm --filter @workspace/api-spec run codegen`
- The backend runs from `artifacts/api-server/backend/` with absolute paths — do not change the artifact.toml run command to relative paths
- The `.deps_installed` sentinel file in `backend/` prevents pip re-installs on every restart
- SQLAlchemy models auto-create tables on startup — Alembic migrations not yet wired for production; use the Replit Publish flow for schema changes
- `create_all` does NOT alter existing tables. New columns on an existing model must be added with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Startup in `main.py` runs idempotent `ALTER TABLE devices ADD COLUMN IF NOT EXISTS` statements (for `ip_address`, `remote_config`, and the logo columns `logo_check_enabled`, `logo_region`, `logo_match_threshold`, `logo_template`, `logo_missing_since`) right after `create_all`, so existing deployments self-heal on boot. When you add a new column to an existing model, add a matching `ADD COLUMN IF NOT EXISTS` line there.
- Non-null columns + a nullable PATCH schema: `DeviceUpdate` allows omitting fields, but `logo_check_enabled`/`logo_match_threshold` are NON-NULL in the DB. `routers/devices.py: update_device` skips explicit `null` for those keys so a stray `null` can't trigger a 500 integrity error. Pydantic `Field(ge/le)` bounds on `LogoRegion`/threshold reject out-of-range values with 422.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
- Backend API docs available at `/api/docs` (FastAPI Swagger UI) when running
