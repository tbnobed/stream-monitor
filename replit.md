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
  - `services/alert_service.py` — Slack/Discord/generic webhook alerting
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
- **Source Streams** (tab on wall): HLS health cards for source stream monitoring.
- **Device Registry** (`/devices`): Full CRUD for OTT devices (Roku, Fire TV, Chromecast, Apple TV, other).
- **HLS Stream Registry** (`/hls-streams`): Full CRUD for HLS source streams.
- **Incidents** (`/incidents`): Global incident feed with filtering, acknowledge, and per-item uptime %/MTTR.
- **Settings** (`/settings`): All endpoints, intervals, thresholds, and webhook URLs — editable via UI.

## Adding a device

Go to `/devices` → "Add Device". Fill in name, platform, and SRS stream key. The wall renders from DB — no code changes needed.

## Adding an HLS stream

Go to `/hls-streams` → "Add Stream". Enter name and master `.m3u8` URL. Health checks start automatically.

## Configuring alerts

Go to `/settings`. Paste Slack/Discord/generic webhook URLs. Toggle `alerts_enabled` and `alert_on_warning`. Save.

## How SRS WHEP playback works

1. Browser initiates WebRTC via `SrsRtcWhipWhepAsync` pointing at `/api/proxy/whep?stream={key}`
2. FastAPI forwards the SDP offer to the real SRS WHEP endpoint (`http://cdn1.obedtv.live:2023/rtc/v1/whep/?app=live&stream={key}`)
3. SDP answer returns through the proxy back to the browser
4. Video plays over WebRTC — always HTTPS, never mixed-content

## How HLS detection works

Every 30s (configurable): manifest fetch → rendition audit → media-sequence stall check → segment fetch → optional ffprobe decode → DRM key check. All metrics stored in `check_results.detail` JSON.

## How device detection works

Every 15s (configurable): SRS API publisher check + ffmpeg blackdetect/freezedetect/silencedetect on the RTMP ingest URL. Frame thumbnail captured on DOWN/WARNING transitions.

## Dependencies

- `ffmpeg` and `ffprobe` must be available on PATH for device workers and HLS deep validation
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
- `create_all` does NOT alter existing tables. New columns on an existing model (e.g. `devices.ip_address`, `devices.remote_config`) must be added with a manual `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` against the dev DB, or the API server crashes on boot

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
- Backend API docs available at `/api/docs` (FastAPI Swagger UI) when running
