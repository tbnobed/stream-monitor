import asyncio
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Device, Setting
from services.incident_service import handle_status_change
import httpx
import logging

from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration

logger = logging.getLogger(__name__)

# aiortc/aioice are extremely chatty (per-ICE-candidate and per-undecodable-H264
# packet); silence the noise so worker logs stay readable.
for _noisy in ("aioice.ice", "aiortc.codecs.h264", "aiortc.rtcrtpreceiver"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

# Limit concurrent WHEP media probes to avoid resource exhaustion.
probe_semaphore = asyncio.Semaphore(4)

# A stream is considered loading once this many decoded media frames arrive.
FRAME_THRESHOLD = 3


def get_setting(db: Session, key: str, default: str) -> str:
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s else default


async def probe_whep(whep_base: str, app: str, stream_key: str, timeout: float = 8.0) -> dict:
    """Open a real WebRTC (WHEP) connection to SRS and confirm media is flowing.

    SRS returns 201 for the signaling handshake even when a stream does not
    exist, so the only reliable health signal is whether decoded media frames
    actually arrive. Returns a detail dict with the outcome.
    """
    async with probe_semaphore:
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        frames = {"video": 0, "audio": 0}
        reader_tasks: list[asyncio.Task] = []

        @pc.on("track")
        def on_track(track):
            async def reader():
                while True:
                    try:
                        await track.recv()
                        frames[track.kind] += 1
                    except Exception:
                        break
            reader_tasks.append(asyncio.ensure_future(reader()))

        detail: dict = {"whep_url": f"{whep_base}/rtc/v1/whep/?app={app}&stream={stream_key}"}
        try:
            pc.addTransceiver("video", direction="recvonly")
            pc.addTransceiver("audio", direction="recvonly")
            await pc.setLocalDescription(await pc.createOffer())

            url = f"{whep_base}/rtc/v1/whep/?app={app}&stream={stream_key}"
            answer_sdp = None
            http_status = None
            async with httpx.AsyncClient(timeout=6) as client:
                # SRS may edge-pull on the first request and return a transient
                # 502; retry once before giving up. Keep the budget small so a
                # check comfortably fits inside the worker interval.
                for attempt in range(2):
                    resp = await client.post(
                        url,
                        content=pc.localDescription.sdp,
                        headers={"Content-Type": "application/sdp"},
                    )
                    http_status = resp.status_code
                    if resp.status_code in (200, 201):
                        answer_sdp = resp.text
                        break
                    await asyncio.sleep(1.5)

            detail["http_status"] = http_status
            if not answer_sdp:
                detail["media_flowing"] = False
                return detail

            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=answer_sdp, type="answer")
            )

            loop = asyncio.get_event_loop()
            deadline = loop.time() + timeout
            while loop.time() < deadline:
                if frames["video"] >= FRAME_THRESHOLD or frames["audio"] >= FRAME_THRESHOLD:
                    break
                await asyncio.sleep(0.25)

            detail["video_frames"] = frames["video"]
            detail["audio_frames"] = frames["audio"]
            detail["ice_state"] = pc.iceConnectionState
            detail["media_flowing"] = (
                frames["video"] >= FRAME_THRESHOLD or frames["audio"] >= FRAME_THRESHOLD
            )
            return detail
        except Exception as e:
            detail["error"] = str(e)
            detail["media_flowing"] = False
            return detail
        finally:
            for t in reader_tasks:
                t.cancel()
            if reader_tasks:
                await asyncio.gather(*reader_tasks, return_exceptions=True)
            try:
                await pc.close()
            except Exception:
                pass


async def check_device(device_id: int):
    """Health = can we actually load video/audio from the device's WHEP address."""
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device or not device.enabled:
            return

        whep_base = get_setting(db, "srs_whep_base_url", "http://cdn1.obedtv.live:2023")

        try:
            # Hard cap so a single stuck probe can never overrun the worker
            # interval and stall the whole batch.
            detail = await asyncio.wait_for(
                probe_whep(whep_base, device.srs_app, device.srs_stream_key),
                timeout=13.0,
            )
        except asyncio.TimeoutError:
            detail = {"media_flowing": False, "error": "probe timeout"}

        if detail.get("media_flowing"):
            new_status = "HEALTHY"
            reason = ""
        elif detail.get("http_status") not in (200, 201):
            new_status = "DOWN"
            reason = f"WHEP handshake failed (HTTP {detail.get('http_status')})"
        else:
            new_status = "DOWN"
            reason = "No media on WHEP stream"

        await handle_status_change(db, "device", device_id, new_status, reason, detail, None)
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
