import asyncio
import math
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Device, Setting
from services.incident_service import handle_status_change
from services import logo as logo_svc
import httpx
import logging
import numpy as np

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

# Need at least this many judged frames before trusting a black/freeze/silence
# verdict — too few samples is noise, so we fail open instead.
CONTENT_MIN_FRAMES = 3

# Fraction of judged frames that must be bad before we call it a sustained problem.
CONTENT_BAD_RATIO = 0.85

# Freeze is judged over time, not frame-to-frame. Comparing immediately-consecutive
# frames at full frame rate makes low-motion live content (a locked-off camera on a
# speaker) read as "frozen" because per-frame change is tiny. We instead compare each
# frame against a reference grabbed at least this many seconds earlier: real content
# accumulates clear change over a second, while a true freeze stays ~0 even seconds apart.
FREEZE_INTERVAL_SECONDS = 1.0


def get_setting(db: Session, key: str, default: str) -> str:
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s else default


def get_setting_float(db: Session, key: str, default: float) -> float:
    """Numeric setting with a safe fallback so one operator typo can't abort a check."""
    try:
        return float(get_setting(db, key, str(default)))
    except (TypeError, ValueError):
        return default


async def probe_whep(
    whep_base: str,
    app: str,
    stream_key: str,
    timeout: float = 8.0,
    content: dict | None = None,
    logo: dict | None = None,
    sample_seconds: float | None = None,
) -> dict:
    """Open a real WebRTC (WHEP) connection to SRS and confirm media is flowing.

    SRS returns 201 for the signaling handshake even when a stream does not
    exist, so the only reliable health signal is whether decoded media frames
    actually arrive. Returns a detail dict with the outcome.

    When ``content`` is provided, the *already-decoded* WHEP frames are also
    inspected for a dead program — black/frozen video or silent audio — so we
    catch a device stuck on a black or frozen screen that still streams frames.
    This analyses the exact picture the operator sees over WebRTC, needs no RTMP
    reachability, and therefore works in any environment (dev sandbox + LAN).

    ``content`` keys: ``sample_seconds``, ``black_luma`` (0-255 mean below which a
    frame is black), ``freeze_diff`` (0-255 mean abs diff below which consecutive
    frames are identical), ``silence_dbfs`` (dBFS below which audio is silent).
    """
    # Either kind of frame analysis needs the full sample window so we gather
    # enough video frames to judge the picture/logo.
    analyze = bool(content or logo)
    async with probe_semaphore:
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        frames = {"video": 0, "audio": 0}
        # Per-frame analysis tallies (only populated when analysis is on).
        stats = {
            "video_judged": 0, "black": 0,
            "freeze_judged": 0, "freeze": 0,
            "audio_judged": 0, "silence": 0,
            "logo_judged": 0, "logo_match": 0, "logo_score_sum": 0.0,
        }
        freeze_ref = {"small": None, "t": 0.0}
        reader_tasks: list[asyncio.Task] = []

        @pc.on("track")
        def on_track(track):
            async def reader():
                while True:
                    try:
                        frame = await track.recv()
                    except Exception:
                        break
                    frames[track.kind] += 1
                    if not analyze:
                        continue
                    try:
                        if track.kind == "video":
                            gray = frame.to_ndarray(format="gray")
                            if content:
                                # Luminance only; subsample heavily for speed.
                                small = gray[::8, ::8].astype(np.float32)
                                stats["video_judged"] += 1
                                if float(small.mean()) < content["black_luma"]:
                                    stats["black"] += 1
                                # Freeze = no change over a ~1s span, NOT frame-to-frame:
                                # compare against a reference grabbed >= FREEZE_INTERVAL ago.
                                now = asyncio.get_event_loop().time()
                                ref = freeze_ref["small"]
                                if ref is None or ref.shape != small.shape:
                                    freeze_ref["small"] = small
                                    freeze_ref["t"] = now
                                elif now - freeze_ref["t"] >= FREEZE_INTERVAL_SECONDS:
                                    stats["freeze_judged"] += 1
                                    if float(np.abs(small - ref).mean()) < content["freeze_diff"]:
                                        stats["freeze"] += 1
                                    freeze_ref["small"] = small
                                    freeze_ref["t"] = now
                            if logo:
                                crop = logo_svc.crop_region(gray, logo["region"])
                                if crop.size:
                                    small_logo = logo_svc.resize_gray(crop)
                                    score = logo_svc.ncc(small_logo, logo["template"])
                                    stats["logo_judged"] += 1
                                    stats["logo_score_sum"] += score
                                    if score >= logo["threshold"]:
                                        stats["logo_match"] += 1
                        elif track.kind == "audio" and content:
                            arr = frame.to_ndarray().astype(np.float32)
                            rms = float(np.sqrt(np.mean(arr * arr)))
                            dbfs = 20.0 * math.log10(rms / 32768.0 + 1e-9)
                            stats["audio_judged"] += 1
                            if dbfs < content["silence_dbfs"]:
                                stats["silence"] += 1
                    except Exception:
                        # Frame analysis must never break the media probe.
                        pass
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
            # With frame analysis on, sample the full window so we gather enough
            # video frames to judge the picture/logo (audio alone would otherwise
            # let the loop break early with ~0 video frames). Otherwise just
            # confirm media is flowing and bail fast.
            sample_window = (sample_seconds or 5.0) if analyze else timeout
            deadline = loop.time() + sample_window
            while loop.time() < deadline:
                if not analyze and (
                    frames["video"] >= FRAME_THRESHOLD or frames["audio"] >= FRAME_THRESHOLD
                ):
                    break
                await asyncio.sleep(0.1)

            detail["video_frames"] = frames["video"]
            detail["audio_frames"] = frames["audio"]
            detail["ice_state"] = pc.iceConnectionState
            detail["media_flowing"] = (
                frames["video"] >= FRAME_THRESHOLD or frames["audio"] >= FRAME_THRESHOLD
            )

            if analyze and detail["media_flowing"]:
                detail["content"] = _content_verdict(stats, bool(content), bool(logo))
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


def _content_verdict(stats: dict, content_on: bool, logo_on: bool) -> dict:
    """Turn per-frame tallies into a black/freeze/silence/logo verdict.

    Fails OPEN: a verdict is only positive when we judged enough frames and the
    bad fraction is sustained, so sparse/odd samples never flip a loading stream.
    A black frame is also a frozen frame, so black takes priority in the caller.
    """
    verdict: dict = {"analyzed": True}
    if content_on:
        vj, fj, aj = stats["video_judged"], stats["freeze_judged"], stats["audio_judged"]
        verdict.update({
            "video_judged": vj,
            "audio_judged": aj,
            "black": vj >= CONTENT_MIN_FRAMES and stats["black"] / vj >= CONTENT_BAD_RATIO,
            "freeze": fj >= CONTENT_MIN_FRAMES and stats["freeze"] / fj >= CONTENT_BAD_RATIO,
            "silence": aj >= CONTENT_MIN_FRAMES and stats["silence"] / aj >= CONTENT_BAD_RATIO,
            # Audio flowing but no decodable video at all over the whole window is
            # a strong "no picture" signal — surface it (a notch softer than DOWN).
            "no_video": vj == 0,
        })
    if logo_on:
        lj = stats["logo_judged"]
        match_ratio = (stats["logo_match"] / lj) if lj else 0.0
        verdict.update({
            "logo_judged": lj,
            "logo_score": round(stats["logo_score_sum"] / lj, 3) if lj else None,
            "logo_match_ratio": round(match_ratio, 3),
            # Present if the logo matched in a meaningful fraction of frames;
            # missing only when it's sustained-absent (>=85% of frames lacked it),
            # so a brief occlusion or ad bumper never trips a false alert.
            "logo_present": lj >= CONTENT_MIN_FRAMES and match_ratio > (1.0 - CONTENT_BAD_RATIO),
            "logo_missing": lj >= CONTENT_MIN_FRAMES and match_ratio <= (1.0 - CONTENT_BAD_RATIO),
        })
    return verdict


async def check_device(device_id: int):
    """Health = can we actually load video/audio from the device's WHEP address."""
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device or not device.enabled:
            return

        whep_base = get_setting(db, "srs_whep_base_url", "http://cdn1.obedtv.live:2023")

        # Build the content-analysis config up front so the probe can inspect the
        # decoded WHEP frames for a dead program (black/freeze/silence) in the
        # same pass it confirms media is flowing. Thresholds reuse the existing
        # Settings keys, reinterpreted for per-frame analysis (fractions -> 0-255).
        content_enabled = get_setting(db, "device_content_check_enabled", "true").lower() == "true"
        content_cfg = None
        # Clamp to a sane floor: a 0/negative window would skip frame sampling
        # entirely (media_flowing=False) and falsely mark a healthy stream DOWN.
        sample_seconds = max(1.0, get_setting_float(db, "device_content_sample_seconds", 5.0))
        if content_enabled and device.srs_stream_key:
            sil_raw = get_setting(db, "silencedetect_noise", "-50dB").strip().lower().replace("db", "")
            try:
                silence_dbfs = float(sil_raw)
            except (TypeError, ValueError):
                silence_dbfs = -50.0
            content_cfg = {
                "sample_seconds": sample_seconds,
                "black_luma": get_setting_float(db, "blackdetect_threshold", 0.10) * 255.0,
                "freeze_diff": get_setting_float(db, "freezedetect_noise", 0.003) * 255.0,
                "silence_dbfs": silence_dbfs,
            }

        # Per-device logo-presence check. Only active when enabled AND a reference
        # template has been captured (no template -> never alerts, fail-safe).
        logo_cfg = None
        if device.logo_check_enabled and device.logo_template and device.logo_region:
            template = logo_svc.decode_template(device.logo_template)
            if template is not None:
                logo_cfg = {
                    "region": device.logo_region,
                    "template": template,
                    "threshold": float(device.logo_match_threshold or 0.6),
                }

        try:
            # Hard cap so a single stuck probe can never overrun the worker
            # interval and stall the whole batch. With frame analysis on, the
            # probe samples for the full window, so widen the cap accordingly.
            analyze = bool(content_cfg or logo_cfg)
            probe_timeout = (sample_seconds + 10.0) if analyze else 13.0
            detail = await asyncio.wait_for(
                probe_whep(
                    whep_base, device.srs_app, device.srs_stream_key,
                    content=content_cfg,
                    logo=logo_cfg,
                    sample_seconds=sample_seconds,
                ),
                timeout=probe_timeout,
            )
        except asyncio.TimeoutError:
            detail = {"media_flowing": False, "error": "probe timeout"}

        if detail.get("media_flowing"):
            new_status = "HEALTHY"
            reason = ""
            # The feed loads — now check the actual program (analysed inside the
            # probe from the decoded frames). Fail-open: only flip on a positive
            # detection; black takes priority over freeze (a black frame is also
            # a frozen one).
            content = detail.get("content") or {}
            if content.get("black"):
                new_status, reason = "DOWN", "Black screen on device output"
            elif content.get("freeze"):
                new_status, reason = "DOWN", "Frozen frame on device output"
            elif content.get("logo_missing"):
                new_status, reason = "DOWN", "Expected logo not detected"
            elif content.get("no_video"):
                new_status, reason = "WARNING", "No video frames on device output"
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
