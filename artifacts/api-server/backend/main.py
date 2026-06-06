import os
import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from database import Base, engine
from routers import devices, hls_streams, check_results, incidents, settings, dashboard, proxy, sse, guacamole_sessions, remote, auth, users, mobile_remote
from auth import get_current_user
from config import settings as app_settings
from workers.device_worker import device_worker_loop
from workers.hls_worker import hls_worker_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    Base.metadata.create_all(bind=engine)

    # Self-healing migration: create_all() does NOT add columns to tables that
    # already exist, so columns introduced after the initial deploy must be
    # added explicitly. Idempotent (IF NOT EXISTS), runs before serving traffic.
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS ip_address VARCHAR(64)"))
        conn.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS remote_config JSONB"))
        conn.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS logo_check_enabled BOOLEAN NOT NULL DEFAULT false"))
        conn.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS logo_region JSONB"))
        conn.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS logo_match_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.6"))
        conn.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS logo_template TEXT"))
        conn.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS logo_missing_since TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS black_since TIMESTAMPTZ"))

    # Seed defaults
    from database import SessionLocal
    from routers.settings import ensure_defaults
    from models import Device
    db = SessionLocal()
    ensure_defaults(db)

    # Seed devices if empty
    if db.query(Device).count() == 0:
        from models import Device as D
        seed_devices = [
            D(name="Roku Device", platform="roku", srs_stream_key="vodroku", srs_app="live", enabled=True, notes="HDMI capture of Roku box"),
            D(name="Fire TV Stick", platform="firetv", srs_stream_key="vodfire", srs_app="live", enabled=True, notes="HDMI capture of FireTV"),
            D(name="Chromecast", platform="chromecast", srs_stream_key="vodchrome", srs_app="live", enabled=True, notes="HDMI capture of Chromecast"),
            D(name="Apple TV", platform="appletv", srs_stream_key="vodapple", srs_app="live", enabled=True, notes="HDMI capture of Apple TV"),
        ]
        for d in seed_devices:
            db.add(d)
        logger.info("Seeded 4 devices")

    # Bootstrap the first admin account on a fresh install.
    from models import User
    from auth import hash_password
    if db.query(User).count() == 0:
        admin_password = app_settings.initial_admin_password or secrets.token_urlsafe(16)
        generated = not app_settings.initial_admin_password
        admin = User(
            username=app_settings.initial_admin_username,
            role="admin",
            auth_provider="local",
            password_hash=hash_password(admin_password),
            is_active=True,
        )
        db.add(admin)
        if generated:
            logger.warning(
                "Created initial admin '%s' with a GENERATED one-time password: %s  "
                "-- log in and change it now. Set INITIAL_ADMIN_PASSWORD to choose your own.",
                app_settings.initial_admin_username, admin_password,
            )
        else:
            logger.warning(
                "Created initial admin user '%s'. CHANGE THE PASSWORD after first login.",
                app_settings.initial_admin_username,
            )

    db.commit()
    db.close()

    # Start background workers
    device_task = asyncio.create_task(device_worker_loop())
    hls_task = asyncio.create_task(hls_worker_loop())
    logger.info("Background workers started")

    yield

    # Cleanup
    device_task.cancel()
    hls_task.cancel()
    try:
        await device_task
    except asyncio.CancelledError:
        pass
    try:
        await hls_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="OTT Stream Monitor API",
    version="1.0.0",
    lifespan=lifespan,
    root_path="/api",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Signed-cookie sessions (auth + OIDC state). Falls back to an ephemeral secret
# in dev if SESSION_SECRET is unset (sessions reset on restart).
_session_secret = app_settings.session_secret or secrets.token_hex(32)
if not app_settings.session_secret:
    logger.warning("SESSION_SECRET not set; using an ephemeral secret (sessions reset on restart)")
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    same_site="lax",
    https_only=app_settings.session_cookie_secure,
)

# Auth endpoints are public; everything else requires a valid session.
auth_required = [Depends(get_current_user)]

app.include_router(auth.router)
app.include_router(users.router)  # admin-gated inside the router
app.include_router(devices.router, dependencies=auth_required)
app.include_router(hls_streams.router, dependencies=auth_required)
app.include_router(check_results.router, dependencies=auth_required)
app.include_router(incidents.router, dependencies=auth_required)
app.include_router(settings.router, dependencies=auth_required)
app.include_router(dashboard.router, dependencies=auth_required)
app.include_router(proxy.router, dependencies=auth_required)
app.include_router(sse.router, dependencies=auth_required)
app.include_router(guacamole_sessions.router, dependencies=auth_required)
app.include_router(remote.router, dependencies=auth_required)
# Public, token-scoped phone remote (authority is the QR token itself, not a session).
app.include_router(mobile_remote.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
