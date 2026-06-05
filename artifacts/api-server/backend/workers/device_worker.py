import asyncio
import subprocess
import re
import os
import tempfile
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Device, Setting
from services.incident_service import handle_status_change
import httpx
import logging

logger = logging.getLogger(__name__)

ffmpeg_semaphore = asyncio.Semaphore(4)


def get_setting(db: Session, key: str, default: str) -> str:
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s else default


async def check_srs_publisher(srs_api_base: str, srs_app: str, stream_key: str) -> bool:
    """Check if the stream has an active publisher via SRS API."""
    try:
        url = f"{srs_api_base}/streams/"
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return False
            data = resp.json()
            streams = data.get("streams", [])
            for s in streams:
                if s.get("app") == srs_app and s.get("name") == stream_key:
                    clients = s.get("clients", 0)
                    publish = s.get("publish", {})
                    if publish.get("active", False) or clients > 0:
                        return True
            return False
    except Exception as e:
        logger.warning(f"SRS API check failed: {e}")
        return False


async def run_ffmpeg_analysis(rtmp_url: str, timeout: int = 20) -> dict:
    """Run ffmpeg to detect black/frozen/silent frames."""
    async with ffmpeg_semaphore:
        vf = "blackdetect=d=2:pix_th=0.10,freezedetect=n=-60dB:d=2"
        af = "silencedetect=n=-50dB:d=3"
        cmd = [
            "ffmpeg", "-hide_banner",
            "-i", rtmp_url,
            "-t", "10",
            "-vf", vf,
            "-af", af,
            "-f", "null", "-",
        ]
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=timeout,
            )
            try:
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return {"error": "ffmpeg timeout"}

            stderr_text = stderr.decode("utf-8", errors="replace")
            return {
                "black_detected": "blackdetect" in stderr_text,
                "freeze_detected": "freezedetect" in stderr_text,
                "silence_detected": "silencedetect" in stderr_text and "silence_start" in stderr_text,
                "stderr_snippet": stderr_text[-500:],
            }
        except FileNotFoundError:
            return {"error": "ffmpeg not found"}
        except Exception as e:
            return {"error": str(e)}


async def capture_frame(rtmp_url: str, output_dir: str = "/tmp/frames") -> str | None:
    """Capture a JPEG frame from the stream."""
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    stream_key = rtmp_url.split("/")[-1]
    filename = f"{stream_key}_{ts}.jpg"
    output_path = os.path.join(output_dir, filename)

    cmd = [
        "ffmpeg", "-hide_banner",
        "-i", rtmp_url,
        "-vframes", "1",
        "-f", "image2",
        output_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=10)
        if os.path.exists(output_path):
            return output_path
    except Exception:
        pass
    return None


async def check_device(device_id: int):
    """Perform a full health check on one device."""
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device or not device.enabled:
            return

        srs_api_base = get_setting(db, "srs_api_base_url", "http://cdn1.obedtv.live:1985/api/v1")
        rtmp_base = get_setting(db, "rtmp_ingest_base_url", "rtmp://cdn1.obedtv.live:1935/live")
        rtmp_url = f"{rtmp_base}/{device.srs_stream_key}"

        detail = {}
        frame_path = None

        # 1. SRS API publisher check
        has_publisher = await check_srs_publisher(srs_api_base, device.srs_app, device.srs_stream_key)
        detail["has_publisher"] = has_publisher

        if not has_publisher:
            new_status = "DOWN"
            reason = "No publisher"
        else:
            # 2. ffmpeg frame analysis
            ffmpeg_result = await run_ffmpeg_analysis(rtmp_url)
            detail.update(ffmpeg_result)

            black = ffmpeg_result.get("black_detected", False)
            frozen = ffmpeg_result.get("freeze_detected", False)
            silent = ffmpeg_result.get("silence_detected", False)

            if black:
                new_status = "DOWN"
                reason = "Black frame detected"
            elif frozen:
                new_status = "DOWN"
                reason = "Frozen frame detected"
            elif silent:
                new_status = "WARNING"
                reason = "Audio silence detected"
            elif ffmpeg_result.get("error"):
                new_status = "WARNING"
                reason = f"ffmpeg error: {ffmpeg_result['error']}"
            else:
                new_status = "HEALTHY"
                reason = ""

            # Capture frame on DOWN/WARNING transition
            if new_status in ("DOWN", "WARNING") and device.current_status == "HEALTHY":
                frame_path = await capture_frame(rtmp_url)

        await handle_status_change(
            db, "device", device_id, new_status, reason, detail, frame_path
        )
    except Exception as e:
        logger.error(f"Device check error for device {device_id}: {e}")
    finally:
        db.close()


async def device_worker_loop():
    """Main device worker loop."""
    logger.info("Device health worker started")
    while True:
        db = SessionLocal()
        try:
            interval = int(get_setting(db, "device_check_interval", "15"))
            devices = db.query(Device).filter(Device.enabled == True).all()
            device_ids = [d.id for d in devices]
        except Exception as e:
            logger.error(f"Device worker error fetching devices: {e}")
            device_ids = []
            interval = 15
        finally:
            db.close()

        tasks = [check_device(did) for did in device_ids]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        await asyncio.sleep(interval)
