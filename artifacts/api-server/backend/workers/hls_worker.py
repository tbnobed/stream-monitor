import asyncio
import httpx
import m3u8
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from models import HlsStream, Setting
from services.incident_service import handle_status_change
import logging

logger = logging.getLogger(__name__)

ffprobe_semaphore = asyncio.Semaphore(4)


def get_setting(db: Session, key: str, default: str) -> str:
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s else default


async def check_manifest(url: str) -> dict:
    """Fetch and validate the master .m3u8 manifest."""
    start = datetime.utcnow()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url)
        latency_ms = (datetime.utcnow() - start).total_seconds() * 1000

        if resp.status_code != 200:
            return {"ok": False, "reason": f"Manifest HTTP {resp.status_code}", "latency_ms": latency_ms}

        text = resp.text
        if not text.strip().startswith("#EXTM3U"):
            return {"ok": False, "reason": "Invalid manifest (missing #EXTM3U)", "latency_ms": latency_ms}

        playlist = m3u8.loads(text)
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "is_master": playlist.is_endlist is False and len(playlist.playlists) > 0,
            "playlists": [p.uri for p in playlist.playlists],
            "rendition_count": len(playlist.playlists),
            "raw_text": text,
        }
    except Exception as e:
        return {"ok": False, "reason": f"Manifest fetch failed: {e}"}


async def fetch_variant_playlist(uri: str, base_url: str) -> dict:
    """Fetch a variant playlist and return media sequence + latest segment."""
    if not uri.startswith("http"):
        base = base_url.rsplit("/", 1)[0]
        uri = f"{base}/{uri}"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(uri)
        if resp.status_code != 200:
            return {"ok": False, "reason": f"Variant HTTP {resp.status_code}"}

        playlist = m3u8.loads(resp.text)
        segments = playlist.segments
        media_seq = playlist.media_sequence or 0
        latest_segment = segments[-1].uri if segments else None

        return {
            "ok": True,
            "media_sequence": media_seq,
            "segment_count": len(segments),
            "latest_segment": latest_segment,
            "base_uri": uri.rsplit("/", 1)[0],
        }
    except Exception as e:
        return {"ok": False, "reason": str(e)}


async def check_segment(segment_uri: str, base_uri: str) -> dict:
    """Download and validate a segment."""
    if not segment_uri.startswith("http"):
        segment_uri = f"{base_uri}/{segment_uri}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(segment_uri)
        if resp.status_code != 200:
            return {"ok": False, "reason": f"Segment HTTP {resp.status_code}"}
        size = len(resp.content)
        if size == 0:
            return {"ok": False, "reason": "Segment is empty"}
        return {"ok": True, "size_bytes": size}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


async def ffprobe_segment(segment_uri: str, base_uri: str) -> dict:
    """Run ffprobe on a segment for deep validation."""
    async with ffprobe_semaphore:
        if not segment_uri.startswith("http"):
            segment_uri = f"{base_uri}/{segment_uri}"
        cmd = [
            "ffprobe", "-hide_banner", "-v", "quiet",
            "-print_format", "json", "-show_streams",
            segment_uri,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            import json
            data = json.loads(stdout.decode())
            streams = data.get("streams", [])
            has_video = any(s.get("codec_type") == "video" for s in streams)
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
            return {"ok": has_video and has_audio, "has_video": has_video, "has_audio": has_audio}
        except Exception as e:
            return {"ok": False, "reason": str(e)}


async def check_key_server(key_uri: str) -> bool:
    """Check that the HLS key server is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.head(key_uri)
            return resp.status_code < 400
    except Exception:
        return False


async def check_hls_stream(stream_id: int):
    """Full HLS health check for one stream."""
    db = SessionLocal()
    try:
        stream = db.query(HlsStream).filter(HlsStream.id == stream_id).first()
        if not stream or not stream.enabled:
            return

        ffprobe_enabled = get_setting(db, "ffprobe_enabled", "true").lower() == "true"
        stall_threshold = int(get_setting(db, "segment_stall_threshold", "2"))

        detail = {}
        new_status = "HEALTHY"
        reason = ""

        # 1. Master manifest check
        manifest_result = await check_manifest(stream.master_url)
        detail["manifest"] = manifest_result

        if not manifest_result["ok"]:
            new_status = "DOWN"
            reason = manifest_result.get("reason", "Manifest unreachable")
            await handle_status_change(db, "hls_stream", stream_id, new_status, reason, detail)
            return

        playlists = manifest_result.get("playlists", [])
        rendition_count = manifest_result.get("rendition_count", 0)

        # 2. Rendition audit
        if stream.expected_renditions and rendition_count < stream.expected_renditions:
            new_status = "WARNING"
            reason = f"Missing renditions: got {rendition_count}, expected {stream.expected_renditions}"

        # 3. Fetch top variant playlist
        if playlists:
            variant_result = await fetch_variant_playlist(playlists[0], stream.master_url)
            detail["variant"] = variant_result

            if not variant_result["ok"]:
                new_status = "DOWN"
                reason = variant_result.get("reason", "Variant playlist fetch failed")
                await handle_status_change(db, "hls_stream", stream_id, new_status, reason, detail)
                return

            current_seq = variant_result.get("media_sequence", 0)
            detail["media_sequence"] = current_seq

            # 4. Segment stall check
            if stream.last_media_sequence is not None:
                if current_seq == stream.last_media_sequence:
                    stream.stall_check_count += 1
                    if stream.stall_check_count >= stall_threshold:
                        new_status = "DOWN"
                        reason = "Stream stalled (media sequence not advancing)"
                else:
                    stream.stall_check_count = 0
            stream.last_media_sequence = current_seq

            # 5. Segment fetch
            latest_segment = variant_result.get("latest_segment")
            base_uri = variant_result.get("base_uri", "")
            if latest_segment and new_status == "HEALTHY":
                seg_result = await check_segment(latest_segment, base_uri)
                detail["segment"] = seg_result
                if not seg_result["ok"]:
                    new_status = "DOWN"
                    reason = seg_result.get("reason", "Segment fetch failed")

            # 6. ffprobe deep check
            if ffprobe_enabled and latest_segment and new_status == "HEALTHY":
                probe_result = await ffprobe_segment(latest_segment, base_uri)
                detail["ffprobe"] = probe_result
                if not probe_result["ok"]:
                    new_status = "DOWN"
                    reason = "Segment decode failed (ffprobe)"

            # 7. DRM key check
            if stream.is_encrypted and new_status == "HEALTHY":
                raw_text = manifest_result.get("raw_text", "")
                key_uri = None
                for line in raw_text.split("\n"):
                    if "#EXT-X-KEY" in line and "URI=" in line:
                        import re
                        match = re.search(r'URI="([^"]+)"', line)
                        if match:
                            key_uri = match.group(1)
                            break
                if key_uri:
                    key_ok = await check_key_server(key_uri)
                    detail["key_server"] = key_ok
                    if not key_ok:
                        new_status = "DOWN"
                        reason = "Key server unreachable"

        db.add(stream)
        db.commit()

        await handle_status_change(db, "hls_stream", stream_id, new_status, reason, detail)

    except Exception as e:
        logger.error(f"HLS check error for stream {stream_id}: {e}")
    finally:
        db.close()


async def hls_worker_loop():
    """Main HLS worker loop."""
    logger.info("HLS health worker started")
    while True:
        db = SessionLocal()
        try:
            interval = int(get_setting(db, "hls_check_interval", "30"))
            streams = db.query(HlsStream).filter(HlsStream.enabled == True).all()
            stream_ids = [s.id for s in streams]
        except Exception as e:
            logger.error(f"HLS worker error: {e}")
            stream_ids = []
            interval = 30
        finally:
            db.close()

        tasks = [check_hls_stream(sid) for sid in stream_ids]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        await asyncio.sleep(interval)
