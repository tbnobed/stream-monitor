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


def gradient_magnitude(gray: np.ndarray) -> np.ndarray:
    """Sobel gradient magnitude of a grayscale array (float32, same shape).

    We match on EDGE STRUCTURE rather than raw brightness because most channel
    bugs (e.g. TBN) are *semi-transparent watermarks*: their intensity is
    alpha-blended with whatever video is behind them, so a logo that is crisp
    over a dark scene becomes washed-out and low-contrast over a bright/busy one
    — which collapsed the old intensity-NCC score even though the logo was
    clearly present. The letter *edges* survive that blending far better, so
    correlating gradients gives a stable "present/absent" signal across scenes.
    """
    g = gray.astype(np.float32)
    gp = np.pad(g, 1, mode="edge")
    gx = (
        (gp[:-2, 2:] + 2.0 * gp[1:-1, 2:] + gp[2:, 2:])
        - (gp[:-2, :-2] + 2.0 * gp[1:-1, :-2] + gp[2:, :-2])
    )
    gy = (
        (gp[2:, :-2] + 2.0 * gp[2:, 1:-1] + gp[2:, 2:])
        - (gp[:-2, :-2] + 2.0 * gp[:-2, 1:-1] + gp[:-2, 2:])
    )
    return np.sqrt(gx * gx + gy * gy)


def match_score(
    template: np.ndarray, frame_gray: np.ndarray, region: dict | tuple, search: float = 0.25
) -> float:
    """Best NCC of the template against the region, scanning small positional
    offsets so a slightly-misaligned box still locks onto the logo.

    Matching is done on Sobel **gradient magnitude** (see ``gradient_magnitude``)
    rather than raw intensity, so a semi-transparent watermark still correlates
    strongly even when the background behind it changes the logo's brightness.
    The stored template stays raw grayscale; edges are computed on the fly here,
    so existing saved references keep working without re-capture.

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
    t_edge = gradient_magnitude(template)
    best = -1.0
    steps = (-search, 0.0, search)
    for dy in steps:
        for dx in steps:
            crop = crop_region(frame_gray, {"x": x + dx * w, "y": y + dy * h, "w": w, "h": h})
            if crop.size:
                s = ncc(t_edge, gradient_magnitude(resize_gray(crop)))
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


async def _grab_many_once(
    whep_base: str,
    app: str,
    stream_key: str,
    seconds: float,
    max_keep: int = 24,
) -> list[np.ndarray]:
    """One WHEP connect that decodes for the full ``seconds`` window and returns
    up to ``max_keep`` time-spaced RGB frames. Used by ``grab_frames_spread`` to
    get several time-spaced frames from a single connection (one keyframe, no
    per-frame reconnect cost).

    Frames are throttled *as they arrive* (kept at most once every
    ``seconds/max_keep``) rather than buffered wholesale — at OTT resolutions a
    full window would be hundreds of multi-MB RGB arrays, so storing every frame
    risked exhausting memory during a manual capture. We still ``recv()`` every
    frame to drain the track; we just don't retain most of them.
    """
    loop = asyncio.get_event_loop()
    pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    frames: list[np.ndarray] = []
    reader_tasks: list[asyncio.Task] = []
    keep_interval = seconds / max(1, max_keep)

    @pc.on("track")
    def on_track(track):
        async def reader():
            last_kept = float("-inf")
            while True:
                try:
                    frame = await track.recv()
                except Exception:
                    break
                if track.kind != "video":
                    continue
                now = loop.time()
                if now - last_kept < keep_interval or len(frames) >= max_keep:
                    continue
                try:
                    frames.append(frame.to_ndarray(format="rgb24"))
                    last_kept = now
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
            return []

        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer_sdp, type="answer"))

        loop = asyncio.get_event_loop()
        deadline = loop.time() + seconds
        while loop.time() < deadline:
            await asyncio.sleep(0.1)
        return list(frames)
    except Exception:
        return list(frames)
    finally:
        for t in reader_tasks:
            t.cancel()
        if reader_tasks:
            await asyncio.gather(*reader_tasks, return_exceptions=True)
        try:
            await pc.close()
        except Exception:
            pass


async def grab_frames_spread(
    whep_base: str,
    app: str,
    stream_key: str,
    seconds: float = 10.0,
    count: int = 5,
    retries: int = 2,
) -> list[np.ndarray]:
    """Return up to ``count`` RGB frames evenly spaced across a ``seconds`` window.

    Auto-tightening relies on the logo being *static while the background moves*,
    so we need frames separated in time (adjacent frames are nearly identical and
    give an over-optimistic match). Frames come from one WHEP connection; we
    sub-sample the collected stream by index, which approximates even time
    spacing since frames arrive at a roughly constant rate. Retries on a fresh
    connection if the first attempt yields too few frames.
    """
    frames: list[np.ndarray] = []
    # Keep a bounded, time-spaced pool (a few per requested frame) so the capture
    # never buffers a full window of multi-MB RGB arrays; we then subsample to count.
    max_keep = max(count * 3, 8)
    for attempt in range(max(1, retries)):
        frames = await _grab_many_once(whep_base, app, stream_key, seconds, max_keep=max_keep)
        if len(frames) >= 2:
            break
        if attempt + 1 < max(1, retries):
            await asyncio.sleep(0.5)
    if len(frames) <= count:
        return frames
    idx = np.linspace(0, len(frames) - 1, count).round().astype(int)
    return [frames[i] for i in dict.fromkeys(idx.tolist())]


# Minimum edge-structure (Sobel magnitude std) a candidate crop must have to be
# considered a logo. Featureless/flat regions (e.g. a static dark corner) are
# temporally stable too, so without this floor auto-tighten could lock onto a
# blank patch instead of the actual bug.
_AUTO_TIGHTEN_EDGE_STD_FLOOR = 4.0


# Minimum scene motion (mean abs luma diff, 0..255) across the captured window
# for temporal logo-localization to be trustworthy. A logo is told apart from
# background by being *static while the background changes*; if the whole scene
# barely moved during capture (a still ad/slate), every sub-box is equally
# stable and the search cannot separate logo from background — so we refuse to
# tighten rather than confidently store a loose box.
_AUTO_TIGHTEN_MOTION_MIN = 2.0


def auto_tighten_region(
    frames_gray: list[np.ndarray],
    rough: dict,
    margin: float = 0.15,
    accept: float = 0.6,
) -> tuple[dict, dict]:
    """Snap an operator's roughly-drawn box to the tight logo inside it.

    A loose or slightly-misplaced box is the #1 cause of false "logo missing"
    alerts: the stored template ends up mostly *background*, so later frames
    (different background) score low. The fix is to have the server localize the
    logo itself. We grid-search sub-boxes within the rough box (expanded by
    ``margin`` on each side, so an offset box can still reach a logo that pokes
    out) and keep the box whose template from the first frame stays most
    consistent across the *other* time-spaced frames — the logo is static while
    the background changes, so its box has the highest consistency. Consistency is
    a *trimmed mean* of the per-frame gradient-NCCs (the single worst frame is
    dropped when there are >=3 others): semi-transparent watermarks wash out for
    one frame during a hard cut to a bright/busy scene, and scoring on the raw
    minimum would reject the real logo outright. Among boxes tied at the top
    consistency we keep the *smallest*: it squeezes the box
    down onto just the logo. A gradient-energy floor rejects flat/dark patches
    that are stable but featureless, which is what makes the smallest-box rule
    safe even in near-black scenes — there, only logo-containing boxes have any
    edges at all, so the tightest structured box lands exactly on the bug
    (matching on raw NCC alone would keep an oversized box, since a dark
    background contributes almost no gradient to dilute the score).

    Crucially this only works when the scene actually moved during capture, so we
    gate on ``_AUTO_TIGHTEN_MOTION_MIN``: in a near-static window every box looks
    stable and tightening would be a coin-flip, so we decline and tell the
    operator to capture during live programming.

    Returns ``(region, stats)``. ``region`` is the tightened box, or the original
    ``rough`` when motion is too low or no candidate clears ``accept`` (fail-safe:
    a save never makes detection worse). ``stats`` carries ``tightened`` (bool),
    the winning ``best_min`` NCC, the measured ``motion``, and a ``reason``.
    """
    rough = {"x": float(rough["x"]), "y": float(rough["y"]), "w": float(rough["w"]), "h": float(rough["h"])}
    usable = [f for f in frames_gray if f is not None and f.size]
    if len(usable) < 2:
        return rough, {"tightened": False, "reason": "need >=2 frames"}

    base_full = usable[0].astype(np.float32)
    motion = max(float(np.abs(f.astype(np.float32) - base_full).mean()) for f in usable[1:])
    if motion < _AUTO_TIGHTEN_MOTION_MIN:
        return rough, {
            "tightened": False,
            "reason": "static scene — capture during live programming",
            "motion": round(motion, 3),
        }

    rx, ry, rw, rh = rough["x"], rough["y"], rough["w"], rough["h"]
    sx0 = max(0.0, rx - margin * rw)
    sx1 = min(1.0, rx + rw + margin * rw)
    sy0 = max(0.0, ry - margin * rh)
    sy1 = min(1.0, ry + rh + margin * rh)

    w_opts = sorted({max(0.02, round(f * rw, 4)) for f in (0.3, 0.45, 0.6, 0.8, 1.0)})
    h_opts = sorted({max(0.02, round(f * rh, 4)) for f in (0.3, 0.45, 0.6, 0.8, 1.0)})
    grid = 6

    base = usable[0]
    others = usable[1:]
    # Selection key is (consistency-bucket, -area): pick the most temporally
    # consistent box and, among ties, the *smallest* — squeezing onto the logo.
    best = None  # (bucket, neg_area, region, robust_ncc, min_ncc)
    for cw in w_opts:
        if cw > sx1 - sx0:
            continue
        for ch in h_opts:
            if ch > sy1 - sy0:
                continue
            for cx in np.linspace(sx0, sx1 - cw, grid):
                for cy in np.linspace(sy0, sy1 - ch, grid):
                    reg = {"x": float(cx), "y": float(cy), "w": float(cw), "h": float(ch)}
                    crop = crop_region(base, reg)
                    if crop.size == 0:
                        continue
                    t_edge = gradient_magnitude(resize_gray(crop))
                    if float(t_edge.std()) < _AUTO_TIGHTEN_EDGE_STD_FLOOR:
                        continue
                    scores = []
                    for fr in others:
                        oc = crop_region(fr, reg)
                        if oc.size == 0:
                            scores = None
                            break
                        scores.append(ncc(t_edge, gradient_magnitude(resize_gray(oc))))
                    if not scores:
                        continue
                    ss = sorted(scores)
                    # Trimmed consistency: drop the single worst frame (a hard cut
                    # that washes out a semi-transparent logo) when we have enough.
                    robust = float(np.mean(ss[1:])) if len(ss) >= 3 else float(ss[0])
                    bucket = round(robust, 2)
                    key = (bucket, -(cw * ch))
                    if best is None or key > (best[0], best[1]):
                        best = (bucket, -(cw * ch), reg, robust, float(ss[0]))

    if best is None:
        return rough, {"tightened": False, "reason": "no textured candidate", "motion": round(motion, 3)}
    _, _, reg, robust, worst = best
    if robust < accept:
        return rough, {
            "tightened": False,
            "reason": "weak match",
            "best_robust": round(robust, 3),
            "best_min": round(worst, 3),
            "motion": round(motion, 3),
        }
    return reg, {
        "tightened": True,
        "best_robust": round(robust, 3),
        "best_min": round(worst, 3),
        "motion": round(motion, 3),
    }


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
