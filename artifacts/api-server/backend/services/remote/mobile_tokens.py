"""In-memory store for one-time mobile-remote tokens.

A desktop operator opens a device's remote modal and generates a short-lived,
single-device token. The token is encoded in a QR code; scanning it opens a
touch-friendly remote page on a phone that controls *only* that device, without
a login session.

The token's authority is the secret itself (256-bit urlsafe), scoped to one
device, and short-lived. The desktop modal keeps it alive with a heartbeat and
revokes it when the device window closes; the TTL is a backstop for a crashed
or force-closed browser.

State is process-local (a dict), which matches the rest of the remote layer
(pairing sessions are also in-memory) and the single-uvicorn-process deploy.
"""
import secrets
import threading
import time

# TTL refreshed by the desktop heartbeat. Long enough to survive a missed
# heartbeat or two, short enough that an abandoned token dies on its own.
DEFAULT_TTL_SECONDS = 90

_tokens: dict[str, dict] = {}
_lock = threading.Lock()


def _prune_locked(now: float) -> None:
    expired = [t for t, v in _tokens.items() if v["expires_at"] <= now]
    for t in expired:
        _tokens.pop(t, None)


def create(device_id: int, ttl: int = DEFAULT_TTL_SECONDS) -> tuple[str, int]:
    """Create a token bound to a device. Returns (token, ttl_seconds)."""
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _lock:
        _prune_locked(now)
        _tokens[token] = {"device_id": device_id, "expires_at": now + ttl}
    return token, ttl


def resolve(token: str) -> int | None:
    """Return the device_id for a live token, or None if unknown/expired."""
    now = time.monotonic()
    with _lock:
        entry = _tokens.get(token)
        if entry is None:
            return None
        if entry["expires_at"] <= now:
            _tokens.pop(token, None)
            return None
        return entry["device_id"]


def touch(token: str, device_id: int, ttl: int = DEFAULT_TTL_SECONDS) -> bool:
    """Extend a token's TTL if it exists and belongs to device_id."""
    now = time.monotonic()
    with _lock:
        entry = _tokens.get(token)
        if entry is None or entry["expires_at"] <= now:
            _tokens.pop(token, None)
            return False
        if entry["device_id"] != device_id:
            return False
        entry["expires_at"] = now + ttl
        return True


def revoke(token: str) -> None:
    """Invalidate a token immediately. Idempotent."""
    with _lock:
        _tokens.pop(token, None)
