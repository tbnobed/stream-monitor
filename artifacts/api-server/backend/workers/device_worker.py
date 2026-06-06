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

# Limit concurrent ffmpeg content-analysis processes (separate from WHEP probes).
ffmpeg_semaphore = asyncio.Semaphore(4)

# A stream is considered loading once this many decoded media frames arrive.
FRAME_THRESHOLD = 3


def get_setting(db: Session, key: str, default: str) -> str:
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s else default


def get_setting_float(db: Session, key: str, default: float) -> float:
    """Numeric setting with a safe fallback so one operator typo can't abort a check."""
    try:
        return float(get_setting(db, key, str(default)))
    except (TypeError, ValueError):
        return default


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


async def analyze_device_content(
    rtmp_url: str,
    sample_seconds: float,
    black_d: float,
    black_th: float,
    freeze_n: float,
    freeze_d: float,
    sil_n: str,
    sil_d: float,
) -> dict:
    """Inspect the device's ACTUAL program, not just that the feed loads.

    WHEP frames flowing only proves the capture pipeline is up — a device stuck
    on a black screen, a frozen frame, or a silent spinner still delivers frames
    and would otherwise read HEALTHY. This pulls a few seconds of the device's
    RTMP ingest and runs ffmpeg blackdetect/freezedetect (video) + silencedetect
    (audio). Each filter only emits when its duration threshold is exceeded, so a
    marker means a *sustained* problem.

    Fails OPEN: any tooling/pull error returns analyzed=False and never flips a
    loading stream to DOWN just because ffmpeg could not read it.
    """
    vf = f"blackdetect=d={black_d}:pix_th={black_th},freezedetect=n={freeze_n}:d={freeze_d}"
    af = f"silencedetect=n={sil_n}:d={sil_d}"
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        # Abort fast if the ingest can't be reached / stalls, instead of hanging
        # until our asyncio kill (keeps the worker loop responsive).
        "-rw_timeout", "8000000",
        "-i", rtmp_url,
        "-t", str(sample_seconds),
        "-vf", vf,
        "-af", af,
        "-f", "null", "-",
    ]
    async with ffmpeg_semaphore:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return {"analyzed": False, "error": "ffmpeg not found"}
        try:
            _, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=sample_seconds + 12
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return {"analyzed": False, "error": "content analysis timeout"}

        text = stderr.decode(errors="ignore")
        if "Input #0" not in text:
            return {
                "analyzed": False,
                "error": "could not open device stream",
                "returncode": proc.returncode,
            }
        return {
            "analyzed": True,
            "black": "black_start" in text,
            "freeze": "freeze_start" in text,
            "silence": "silence_start" in text,
        }


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
            # The feed loads — now verify the actual program is alive
            # (black/freeze/silence), not just that frames arrive.
            content_enabled = get_setting(db, "device_content_check_enabled", "true").lower() == "true"
            if content_enabled and device.srs_stream_key:
                rtmp_base = get_setting(db, "rtmp_ingest_base_url", "rtmp://cdn1.obedtv.live:1935/live")
                rtmp_url = f"{rtmp_base.rstrip('/')}/{device.srs_stream_key}"
                sample_seconds = get_setting_float(db, "device_content_sample_seconds", 5.0)
                try:
                    content = await asyncio.wait_for(
                        analyze_device_content(
                            rtmp_url,
                            sample_seconds,
                            get_setting_float(db, "blackdetect_duration", 2.0),
                            get_setting_float(db, "blackdetect_threshold", 0.10),
                            get_setting_float(db, "freezedetect_noise", 0.003),
                            get_setting_float(db, "freezedetect_duration", 2.0),
                            get_setting(db, "silencedetect_noise", "-50dB"),
                            get_setting_float(db, "silencedetect_duration", 3.0),
                        ),
                        timeout=sample_seconds + 15,
                    )
                except asyncio.TimeoutError:
                    content = {"analyzed": False, "error": "content analysis timeout"}
                detail["content"] = content
                # Fail-open: only flip on a positive detection.
                if content.get("black"):
                    new_status, reason = "DOWN", "Black screen on device output"
                elif content.get("freeze"):
                    new_status, reason = "DOWN", "Frozen frame on device output"
                elif content.get("silence"):
                    new_status, reason = "WARNING", "Silent audio on device output"
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
