# OTT Stream Monitor

A full-stack broadcast NOC (Network Operations Center) tool that monitors live OTT device streams (Roku, Fire TV, Chromecast, Apple TV) via WebRTC and HLS source streams, with native on-screen remote control of each device. Replaces a WordPress monitoring wall.

> Deep design rationale for the detection algorithms lives in code comments and in `.agents/memory/` topic files (srs-whep-playback, device-content-monitoring, logo-presence-detection, qr-phone-remote, etc.). This README keeps the operational facts and config knobs.

## Run & Operate

- **Frontend**: served at `/` via the `artifacts/ott-monitor: web` workflow
- **Backend**: served at `/api` via the `artifacts/api-server: API Server` workflow (logs in that workflow console)

## Stack

- **Frontend**: React + Vite, TypeScript, Tailwind, TanStack Query, wouter
- **Backend**: Python FastAPI, SQLAlchemy ORM (tables auto-created on startup)
- **DB**: PostgreSQL (Replit managed)
- **WebRTC**: SRS official WHEP SDK (`/public/srs.sdk.js`); **HLS**: hls.js (optional eyeball view)
- **Real-time**: Server-Sent Events (SSE) at `/api/stream/status`

## Where things live

- `artifacts/ott-monitor/src/` — React frontend (pages, components, hooks)
- `artifacts/api-server/backend/` — FastAPI app
  - `main.py` — entrypoint, startup (DB init, idempotent ALTERs, seeding, background workers)
  - `models.py` / `schemas.py` — SQLAlchemy models / Pydantic schemas
  - `routers/` — route handlers (devices, hls_streams, incidents, settings, dashboard, proxy, sse, remote, auth, users, mobile_remote)
  - `services/remote/` — native remote drivers + `get_driver` factory
  - `services/` — `incident_service.py` (debounce + open/close), `alert_service.py` (webhook + SendGrid), `logo.py` (template/NCC)
  - `workers/` — `device_worker.py` (device health loop), `hls_worker.py` (HLS health loop)
- `lib/api-spec/openapi.yaml` — OpenAPI contract (source of truth); `lib/api-client-react/` — generated React Query hooks

## Architecture decisions

- **HTTPS mixed-content proxy**: All HTTP upstreams (SRS WHEP, SRS API) are proxied through `/api/proxy/*` so the browser only talks HTTPS to our origin. Never hardcode upstream URLs in frontend.
- **Native remote control**: Backend talks directly to each device's LAN IP using its native protocol (Roku ECP, Fire TV ADB, Google TV/Chromecast androidtv, Apple TV Companion). Devices + app server must share one private LAN. Drivers use lazy imports so a missing optional library disables only that platform. Pairing creds live in `Device.remote_config` (JSON), never exposed in API responses.
- **Data-driven**: Every device, HLS stream, endpoint URL, and webhook lives in PostgreSQL. Operators use the UI — never source code.
- **Debounce**: Status changes only after 2 consecutive checks agree (kills flapping). Configurable in Settings.
- **Worker isolation**: Device and HLS workers run as independent async tasks sharing one DB, incident service, SSE feed, and alerting pipeline.
- **SSE + polling dual-mode**: SSE for instant badge updates, 15s React Query polling as reliability fallback.
- **ffmpeg concurrency limit**: Max 4 concurrent ffmpeg/ffprobe processes (configurable).

## Product

- **Monitoring Wall** (`/`): Dense dark grid of device tiles with live WebRTC video, status badges (HEALTHY/WARNING/DOWN/UNKNOWN), bitrate info, `failure_reason` text on DOWN/WARNING, and hover-to-reveal native remote (D-pad, transport, volume, app shortcuts) per tile.
- **Phone remote (QR)**: Desktop remote panel's "Control from phone" button shows a QR encoding a one-time, single-device token URL (`/m/<token>`). Scanning opens a touch remote (`pages/MobileRemote.tsx`) controlling only that device, no login. Token is short-lived (90s TTL, 30s desktop heartbeat) and revoked when the panel closes.
- **Source Streams** (tab on wall): HLS health cards.
- **Device Registry** (`/devices`) / **HLS Stream Registry** (`/hls-streams`): full CRUD.
- **Incidents** (`/incidents`): global feed with filtering, acknowledge, per-item uptime %/MTTR.
- **Settings** (`/settings`, admin): all endpoints, intervals, thresholds, webhook URLs — UI-editable.
- **Users** (`/users`, admin): manage local accounts and roles.

## Authentication

Entire app (frontend + API) is gated. Unauthenticated API calls return 401; the React app shows a login screen until a session exists.

- **Two roles**: `admin` (manage users + edit settings) and `operator` (view + control). Settings PATCH and all `/api/users` routes require admin.
- **Local accounts**: username/password, bcrypt-hashed. On first boot with an empty user table, an initial admin is created from `INITIAL_ADMIN_USERNAME` (default `admin`) + `INITIAL_ADMIN_PASSWORD`. If the password is unset, a random one is generated and logged once on startup (no guessable default). `deploy/install.sh` writes a random one into `deploy/.env` and prints it.
- **Optional Authentik (OIDC) SSO**: enabled only when `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `OIDC_DISCOVERY_URL` are all set; login then shows "Sign in with {OIDC_DISPLAY_NAME}". SSO users auto-provisioned as `operator`. Implemented directly with `httpx` (Authlib is firewall-blocked). Behind a reverse proxy, set `OIDC_REDIRECT_URI` to the public callback URL.
- **Sessions**: signed cookies via Starlette `SessionMiddleware` (`SESSION_SECRET`), `same_site=lax`. Set `SESSION_COOKIE_SECURE=true` only over HTTPS. Frontend is same-origin so cookies are automatic — never set an auth token getter on the API client.
- **Public phone-remote endpoints (token auth, NOT session)**: `routers/mobile_remote.py` is the one router included WITHOUT `get_current_user`. Routes under `/m/{token}` authorize purely on a 256-bit bearer token bound to one device (in-memory, single uvicorn process). `App.tsx` routes `/m/:token` OUTSIDE the auth gate so the phone page never hits the login wall.
- **Layout**: backend `auth.py`, `routers/auth.py`, `routers/users.py`, `config.py`. Frontend `hooks/use-auth.tsx`, `pages/Login.tsx`, `pages/Users.tsx`; `App.tsx` gates routes and re-checks the user on any 401.

## Operating the app

- **Add a device**: `/devices` → "Add Device" (name, platform, SRS stream key). Wall renders from DB.
- **Add an HLS stream**: `/hls-streams` → "Add Stream" (name + master `.m3u8`). Health checks start automatically.
- **Configure alerts**: `/settings` → paste Slack/Discord/Teams/generic webhook URLs, toggle `alerts_enabled` / `alert_on_warning`.
- **Microsoft Teams alerts**: paste a Teams webhook URL into `teams_webhook_url` (`/settings`). Teams will not render arbitrary JSON, so `alert_service.py: _build_teams_payload` sends a Teams-native card and **auto-detects the format from the URL host**: a legacy O365 "Incoming Webhook" connector URL (`*.office.com`) gets a MessageCard; anything else (the current Power Automate "Workflows" trigger, e.g. `*.logic.azure.com`) gets an Adaptive Card envelope. Operators just paste whichever URL Teams gives them. To create one in Teams today: channel → Workflows → "Post to a channel when a webhook request is received" → copy the generated URL.
- **Email alerts (SendGrid)**: fire on the same incident open/resolve events. Set env `SENDGRID_API_KEY` + verified sender `ALERT_FROM_EMAIL` (optionally `ALERT_FROM_NAME`), then recipients in `/settings` → `alert_email_recipients` (comma-separated). Skipped unless key, sender, and ≥1 recipient are all present. Uses `httpx` against SendGrid v3 (`alert_service.py: _send_email_alert`), no SDK.

## How detection works

**SRS WHEP playback**: browser → `SrsRtcWhipWhepAsync` at `/api/proxy/whep?stream={key}` → FastAPI forwards the SDP offer to the real SRS WHEP endpoint (`http://cdn1.obedtv.live:2023/rtc/v1/whep/?app=live&stream={key}`) → answer returns through the proxy → video plays over WebRTC, always HTTPS.

**HLS health** (every 30s, configurable): manifest fetch → rendition audit → media-sequence stall check → segment fetch → optional ffprobe decode → DRM key check. Metrics stored in `check_results.detail` JSON.

**Device health** (every 15s, configurable), two layers — both from the **same WHEP probe** (decoded WebRTC frames, numpy, no RTMP; works in Replit dev *and* LAN):

1. **Feed loads?** Frames actually arriving = capture is up (SRS returns 201 even for non-existent streams, so frames flowing is the only reliable signal).
2. **Program alive?** Per-frame mean luminance → **black**; time-spaced mean abs diff (vs a frame ≥`FREEZE_INTERVAL_SECONDS`/1.0s earlier, NOT the adjacent one) → **freeze**; audio RMS→dBFS → **silence**. Verdicts: frozen → DOWN immediately; black → DOWN only after grace (below); audio but no video sent → WARNING; sustained silence → WARNING.
   - **Black-screen grace**: channels often load a black slate before the show. Black escalates to DOWN only after it's been *continuously* black for `BLACK_GRACE_SECONDS` (**env var**, default 300 = 5 min; `0` = immediate). `Device.black_since` is stamped on the first black cycle and cleared when the picture returns or the feed drops. Freeze is suppressed during the same window (a black screen is also frozen).

- **Fails open**: a negative verdict only fires when ≥3 frames were judged AND the bad fraction is sustained (≥85%); decode errors are swallowed and never cause a false DOWN. Gated by `device_content_check_enabled`; tuned via `device_content_sample_seconds`, `blackdetect_threshold` (×255 black cutoff), `freezedetect_noise` (×255 freeze cutoff), `silencedetect_noise` (dBFS).
- **`no_video` is gated on real video RTP, not decoded-frame count**: aiortc's software H264 decoder can yield 0 decoded frames for a stream that plays fine. After sampling, the probe reads `inbound-rtp` video `packetsReceived` via `pc.getStats()` (`video_rtp_packets`). `no_video` fires only when decoded frames are 0 AND RTP is essentially absent (`< MIN_VIDEO_RTP_PACKETS`, 10); RTP present + 0 decoded → fail open (`content.video_undecoded`).

## Logo-presence detection (per-device, opt-in)

Catches a wrong/lost channel by verifying a fixed on-screen brand logo is still present. Piggybacks on the same WHEP frames (no extra connection).

- **Setup (operator)**: `/devices` → edit → "Logo Presence Monitoring" → toggle on → "Preview region" to grab a live snapshot → **click & drag on the snapshot to draw the region** (X/Y/W/H % inputs stay in sync for fine-tuning) → "Capture & save reference". A *rough* box around the logo is fine — on save the **server auto-tightens** it onto the actual logo (see below). Saving stores a 48×48 grayscale template (base64, internal — never in API), the (tightened) region (fractions), and the threshold on the Device. The capture response returns the final `region` + a `tightened` flag, and the UI snaps the X/Y/W/H inputs to it with a toast.
- **Detection**: each frame's region scored against the template via zero-mean **NCC** with a **drift-tolerant sliding-window match** (`services/logo.py: match_score`, ±25% offsets, best wins). Has the logo when best NCC ≥ `logo_match_threshold` (default 0.6). `logo_missing` → DOWN ("Expected logo not detected"), ordered after black/freeze, before no-video/silence.
- **Fails open**: fires only when ≥3 frames judged AND ≥85% lacked the logo. Disabled / no template = skipped.
- **Grace period (ad breaks)**: `logo_missing` doesn't flip DOWN immediately. `Device.logo_missing_since` stamps the first missing cycle; escalates only after continuously missing for `logo_missing_grace_seconds` (**global Setting**, `/settings`, default 300). Cleared the instant the logo returns / feed drops / check is off — so each ad break gets a full window.
- **Why the box must end up tight (and how the server gets there)**: NCC compares the whole crop, so a loose/offset box gets swamped by the changing picture and the score collapses (loose ≈0.15 vs tight ≈1.0 across a scene change). The operator no longer has to nail it: on save, `services/logo.py: auto_tighten_region` grabs N time-spaced frames over one WHEP connection (`grab_frames_spread`) and grid-searches sub-boxes within (and ±`margin`=0.15 around) the drawn box, keeping the box whose first-frame gradient template stays most **consistent** across the *other* frames (the logo is static, the background isn't). Three rules make this robust: (1) consistency is a **trimmed mean** of per-frame gradient-NCCs (drop the single worst frame) so a hard cut that washes out a semi-transparent watermark for one frame doesn't reject the real logo; (2) among boxes tied at top consistency, keep the **smallest** — squeezes onto just the logo, and works even in near-black scenes because only logo-containing boxes clear the gradient-energy floor (`_AUTO_TIGHTEN_EDGE_STD_FLOOR`); (3) a **motion gate** (`_AUTO_TIGHTEN_MOTION_MIN`) declines to tighten a near-static window (every box looks stable → coin-flip) and tells the operator to capture during live programming. If nothing clears `accept` (0.6) it falls back to the drawn box, so a save never makes detection worse. The stored template is built from the **same first frame** the search scored against. Defaults are a small top-right box (x:85%, y:4%, w:9%, h:6%). Preview shows the live `match_score` so you can set the threshold below it.
- **Data model**: `Device.logo_check_enabled`, `logo_region` (JSON fractions), `logo_match_threshold`, `logo_template` (internal), `logo_missing_since` (internal timer). `DeviceOut` exposes only the computed `logo_reference_set` flag.
- **Capture endpoint**: `POST /devices/{id}/logo/reference` `{region, save, threshold?}` → `snapshot`/`crop` data URLs + `match_score` (live NCC vs the *already-saved* reference, `null` if none) + the final `region` and a `tightened` bool. On `save=true` it auto-tightens (above), persists the tight region + its template, and enables the check. Region/threshold bounds-validated (fractions 0–1).

## Dependencies

- `ffmpeg` / `ffprobe` on PATH for HLS deep validation (device content analysis uses numpy on decoded WebRTC frames, no ffmpeg)
- `numpy` (black/freeze/silence), `pillow` (logo snapshot/crop encoding + template resize), PostgreSQL (Replit-provisioned)

## Self-hosted Docker deployment (Ubuntu LAN)

Native remote control requires the backend on the **same LAN/subnet** as the devices (they reject control from non-private/cross-subnet IPs). `deploy/` packages the app for the user's Ubuntu server.

- `deploy/install.sh` — one-shot installer: installs Docker Engine + Compose, generates `deploy/.env` (random DB password) on first run, then `docker compose up -d --build`. Run `sudo bash deploy/install.sh` from a full repo checkout. **To upgrade: `git pull` then `sudo docker compose up -d --build`.**
- `deploy/docker-compose.yml` — three services, all on `network_mode: host`:
  - `db` — `postgres:16-alpine`, named volume `pgdata`, bound to `127.0.0.1:5432` (not on LAN).
  - `api` — FastAPI (python:3.11-slim + ffmpeg + aiortc). Host networking so outbound traffic carries the host LAN IP and mDNS works. Binds uvicorn to `127.0.0.1:8080` (loopback) so nginx is the only ingress.
  - `web` — nginx serving the built React app + reverse-proxying `/api` (listens :80, proxies to `127.0.0.1:8080`).
- `deploy/.env.example` — template; `POSTGRES_PASSWORD` must match the password in `DATABASE_URL`. Includes `BLACK_GRACE_SECONDS`.
- Routing: nginx serves the SPA at `/`, passes `/api/*` through unchanged (FastAPI `root_path="/api"`). SSE/WebRTC use `proxy_buffering off` + long timeouts.
- **amd64 only**: `pnpm-workspace.yaml` pins frontend platform binaries to linux-x64, so `web` must build on x86_64 (`install.sh` warns otherwise). Frontend uses relative `/api` paths; build only needs `BASE_PATH=/` + a dummy `PORT`.

## Gotchas

- Run codegen after editing `lib/api-spec/openapi.yaml`: `pnpm --filter @workspace/api-spec run codegen`
- Backend runs from `artifacts/api-server/backend/` with absolute paths — don't change artifact.toml to relative paths
- The `.deps_installed` sentinel in `backend/` prevents pip re-installs on every restart
- Alembic not yet wired; `create_all` auto-creates tables but does NOT alter existing ones. New columns on an existing model need an idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `main.py` startup (it already covers `ip_address`, `remote_config`, the `logo_*` columns, `logo_missing_since`, and `black_since`) so existing deployments self-heal. Add a matching line whenever you add a column.
- Non-null columns + nullable PATCH: `logo_check_enabled` / `logo_match_threshold` are NON-NULL in the DB; `routers/devices.py: update_device` skips explicit `null` for those keys so a stray `null` can't 500. Pydantic `Field(ge/le)` bounds reject out-of-range values with 422.

## User preferences

- Self-hosted production runs at vdi.obtv.io. To deploy updates there: `git pull` then `sudo docker compose up -d --build`.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
- Backend API docs at `/api/docs` (FastAPI Swagger UI) when running
