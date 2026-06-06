"""Logo-presence helpers.

A device's stream is expected to always carry a fixed brand logo in a known
region (e.g. a "bug" in the top-right corner). The operator captures a small
grayscale reference template of that region from the live stream; each health
check then crops the same region from the decoded WHEP frames and compares it
to the template with normalized cross-correlation (NCC). When the logo is
sustained-absent, the stream is showing the wrong/lost channel.

Everything here is pure (numpy + Pillow) except ``grab_video_frame``, which
opens a short WHEP (WebRTC) connection to fetch a representative frame for the
capture UI. No RTMP reachability is required, so it works in any environment.
"""
import asyncio
import base64
import io

import httpx
import numpy as np
from PIL import Image
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration

# Fixed comparison size — both the stored template and each live crop are
# resized to this so the match is resolution-independent.
LOGO_TEMPLATE_SIZE = (48, 48)


def _clamp_region(region: dict | tuple, width: int, height: int) -> tuple[int, int, int, int]:
    """Convert a normalized {x,y,w,h} (0..1) region to clamped pixel bounds."""
    if isinstance(region, dict):
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
    else:
        x, y, w, h = region
    x0 = max(0, min(width - 1, int(round(x * width))))
    y0 = max(0, min(height - 1, int(round(y * height))))
    x1 = max(x0 + 1, min(width, int(round((x + w) * width))))
    y1 = max(y0 + 1, min(height, int(round((y + h) * height))))
    return x0, y0, x1, y1


def crop_region(arr: np.ndarray, region: dict | tuple) -> np.ndarray:
    """Crop a grayscale or RGB frame to the given normalized region."""
    h, w = arr.shape[:2]
    x0, y0, x1, y1 = _clamp_region(region, w, h)
    return arr[y0:y1, x0:x1]


def rgb_to_gray(rgb: np.ndarray) -> np.ndarray:
    """Convert an RGB frame to a uint8 grayscale array (luma)."""
    return np.asarray(Image.fromarray(rgb.astype(np.uint8)).convert("L"), dtype=np.uint8)


def resize_gray(gray_crop: np.ndarray) -> np.ndarray:
    """Resize a grayscale crop to the fixed template size, as float32."""
    im = Image.fromarray(gray_crop.astype(np.uint8)).resize(LOGO_TEMPLATE_SIZE)
    return np.asarray(im, dtype=np.float32)


def ncc(a: np.ndarray, b: np.ndarray) -> float:
    """Zero-mean normalized cross-correlation of two same-shape arrays (-1..1).

    Robust to brightness/contrast shifts in the underlying video, so a present
    logo scores high even as the background behind/around it changes.
    """
    a = a.astype(np.float32) - float(a.mean())
    b = b.astype(np.float32) - float(b.mean())
    na = float(np.sqrt((a * a).sum()))
    nb = float(np.sqrt((b * b).sum()))
    if na < 1e-6 or nb < 1e-6:
        return 0.0
    return float((a * b).sum() / (na * nb))


def match_score(
    template: np.ndarray, frame_gray: np.ndarray, region: dict | tuple, search: float = 0.25
) -> float:
    """Best NCC of the template against the region, scanning small positional
    offsets so a slightly-misaligned box still locks onto the logo.

    ``search`` is the max shift tried in each direction as a fraction of the
    region's own width/height. This gives drift tolerance: the operator's box
    no longer has to be pixel-perfect, which was a big source of false
    "logo missing" alerts. Returns -1.0 only if the region is entirely out of
    bounds (no crop had any pixels).
    """
    if isinstance(region, dict):
        x, y, w, h = region["x"], region["y"], region["w"], region["h"]
    else:
        x, y, w, h = region
    best = -1.0
    steps = (-search, 0.0, search)
    for dy in steps:
        for dx in steps:
            crop = crop_region(frame_gray, {"x": x + dx * w, "y": y + dy * h, "w": w, "h": h})
            if crop.size:
                s = ncc(template, resize_gray(crop))
                if s > best:
                    best = s
    return best


def build_template_b64(gray_crop: np.ndarray) -> str:
    """Resize a grayscale crop to the template size and base64-encode raw bytes."""
    small = Image.fromarray(gray_crop.astype(np.uint8)).resize(LOGO_TEMPLATE_SIZE)
    arr = np.asarray(small, dtype=np.uint8)
    return base64.b64encode(arr.tobytes()).decode("ascii")


def decode_template(template_b64: str) -> np.ndarray | None:
    """Decode a stored base64 template back to a float32 array, or None if bad."""
    try:
        raw = base64.b64decode(template_b64)
        w, h = LOGO_TEMPLATE_SIZE
        arr = np.frombuffer(raw, dtype=np.uint8)
        if arr.size != w * h:
            return None
        return arr.reshape(h, w).astype(np.float32)
    except Exception:
        return None


def _encode_data_url(rgb: np.ndarray, fmt: str) -> str:
    im = Image.fromarray(rgb.astype(np.uint8), mode="RGB")
    buf = io.BytesIO()
    save_kwargs = {"quality": 82} if fmt == "JPEG" else {}
    im.save(buf, fmt, **save_kwargs)
    mime = "image/jpeg" if fmt == "JPEG" else "image/png"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def encode_jpeg_data_url(rgb: np.ndarray) -> str:
    return _encode_data_url(rgb, "JPEG")


def encode_png_data_url(rgb: np.ndarray) -> str:
    return _encode_data_url(rgb, "PNG")


async def _grab_once(
    whep_base: str,
    app: str,
    stream_key: str,
    seconds: float,
    want_frames: int,
) -> np.ndarray | None:
    """One WHEP connect → decode attempt. Returns a settled RGB frame or None."""
    pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    frames: list[np.ndarray] = []
    reader_tasks: list[asyncio.Task] = []

    @pc.on("track")
    def on_track(track):
        async def reader():
            while True:
                try:
                    frame = await track.recv()
                except Exception:
                    break
                if track.kind == "video":
                    try:
                        frames.append(frame.to_ndarray(format="rgb24"))
                    except Exception:
                        pass
        reader_tasks.append(asyncio.ensure_future(reader()))

    try:
        pc.addTransceiver("video", direction="recvonly")
        pc.addTransceiver("audio", direction="recvonly")
        await pc.setLocalDescription(await pc.createOffer())

        url = f"{whep_base}/rtc/v1/whep/?app={app}&stream={stream_key}"
        answer_sdp = None
        async with httpx.AsyncClient(timeout=6) as client:
            for _ in range(2):
                resp = await client.post(
                    url,
                    content=pc.localDescription.sdp,
                    headers={"Content-Type": "application/sdp"},
                )
                if resp.status_code in (200, 201):
                    answer_sdp = resp.text
                    break
                await asyncio.sleep(1.5)
        if not answer_sdp:
            return None

        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer_sdp, type="answer"))

        loop = asyncio.get_event_loop()
        deadline = loop.time() + seconds
        while loop.time() < deadline:
            if len(frames) >= want_frames:
                break
            await asyncio.sleep(0.1)

        return frames[-1] if frames else None
    except Exception:
        return None
    finally:
        for t in reader_tasks:
            t.cancel()
        if reader_tasks:
            await asyncio.gather(*reader_tasks, return_exceptions=True)
        try:
            await pc.close()
        except Exception:
            pass


async def grab_video_frame(
    whep_base: str,
    app: str,
    stream_key: str,
    seconds: float = 12.0,
    want_frames: int = 4,
    retries: int = 2,
) -> np.ndarray | None:
    """Open a WHEP connection and return a representative RGB video frame.

    aiortc's *software* H264 decoder needs a keyframe (IDR) to start decoding, so
    a live stream can still yield zero decoded frames inside a short window — e.g.
    when the IDR lands outside it or CPU is contended by the device-worker probes.
    To make interactive capture reliable we (a) wait a generous window and return
    as soon as a few frames settle, and (b) retry on a *fresh* connection, which
    prompts SRS to send a new keyframe. Returns None only when every attempt fails.
    """
    for attempt in range(max(1, retries)):
        frame = await _grab_once(whep_base, app, stream_key, seconds, want_frames)
        if frame is not None:
            return frame
        if attempt + 1 < max(1, retries):
            await asyncio.sleep(0.5)
    return None
