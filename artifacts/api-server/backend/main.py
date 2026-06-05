import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import Base, engine
from routers import devices, hls_streams, check_results, incidents, settings, dashboard, proxy, sse, guacamole_sessions
from workers.device_worker import device_worker_loop
from workers.hls_worker import hls_worker_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    Base.metadata.create_all(bind=engine)

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

# Routers
app.include_router(devices.router)
app.include_router(hls_streams.router)
app.include_router(check_results.router)
app.include_router(incidents.router)
app.include_router(settings.router)
app.include_router(dashboard.router)
app.include_router(proxy.router)
app.include_router(sse.router)
app.include_router(guacamole_sessions.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
