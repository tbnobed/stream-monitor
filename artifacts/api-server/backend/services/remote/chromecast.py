"""Chromecast / Google TV driver — androidtvremote2, PIN pairing.

Modern Chromecast-with-Google-TV devices speak the Android TV remote protocol
(ports 6466/6467), which provides a full D-pad plus app launch via deep links.
Pairing uses a TLS client cert; the device shows a 6-digit PIN on screen.

Note: legacy Chromecast dongles (no on-screen UI) cannot be D-pad controlled and
are not supported by this driver.

Performance note: androidtvremote2 is designed to hold a long-lived connection.
Reconnecting (a TLS handshake) on every key press is slow, so we keep the
connection warm between actions and close it after an idle period, mirroring the
Apple TV driver. Only the first action pays the connect cost.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time

from .base import RemoteDriver, RemoteError, RemoteStatus, PairBeginResult, tcp_open

PAIR_PORT = 6467
CONTROL_PORT = 6466
CLIENT_NAME = "OTT NOC Monitor"

# In-memory pairing sessions keyed by device id (remote + cert/key file paths).
_PAIR_SESSIONS: dict = {}

# In-memory connection cache keyed by device id: live remote, per-device lock,
# last-used timestamp, and the idle-reaper timer handle.
_CONN: dict = {}

# How long a connection is kept open after its last use (seconds).
_CONN_TTL = 300.0

KEY_MAP = {
    "up": "KEYCODE_DPAD_UP",
    "down": "KEYCODE_DPAD_DOWN",
    "left": "KEYCODE_DPAD_LEFT",
    "right": "KEYCODE_DPAD_RIGHT",
    "select": "KEYCODE_DPAD_CENTER",
    "back": "KEYCODE_BACK",
    "home": "KEYCODE_HOME",
    "menu": "KEYCODE_MENU",
    "play_pause": "KEYCODE_MEDIA_PLAY_PAUSE",
    "rewind": "KEYCODE_MEDIA_REWIND",
    "forward": "KEYCODE_MEDIA_FAST_FORWARD",
    "volume_up": "KEYCODE_VOLUME_UP",
    "volume_down": "KEYCODE_VOLUME_DOWN",
    "mute": "KEYCODE_VOLUME_MUTE",
    "power": "KEYCODE_POWER",
}

COMMON_APPS = [
    {"id": "https://www.netflix.com/title", "name": "Netflix"},
    {"id": "https://www.youtube.com", "name": "YouTube"},
    {"id": "https://app.primevideo.com", "name": "Prime Video"},
    {"id": "https://www.disneyplus.com", "name": "Disney+"},
]


def _cert_dir(device_id: int) -> str:
    path = os.path.join(tempfile.gettempdir(), "ott_remote", f"gtv_{device_id}")
    os.makedirs(path, exist_ok=True)
    return path


def _write_cert_files(device_id: int, cert: str, key: str) -> tuple[str, str]:
    d = _cert_dir(device_id)
    certfile = os.path.join(d, "cert.pem")
    keyfile = os.path.join(d, "key.pem")
    with open(certfile, "w") as f:
        f.write(cert)
    with open(keyfile, "w") as f:
        f.write(key)
    return certfile, keyfile


async def _reap_locked(dev_id) -> None:
    """Close an idle connection under the per-device lock.

    Acquiring the lock guarantees no operation is in flight, and the last_used
    re-check avoids closing a connection that was warmed again while this task
    waited for the lock.
    """
    slot = _CONN.get(dev_id)
    if not slot:
        return
    async with slot["lock"]:
        remote = slot.get("remote")
        if remote is None:
            return
        if (time.monotonic() - slot.get("last_used", 0.0)) < _CONN_TTL:
            return
        slot["remote"] = None
        try:
            remote.disconnect()
        except Exception:
            pass


class GoogleTVDriver(RemoteDriver):
    protocol = "androidtv"
    requires_pairing = True
    supports_app_launch = True
    keys = list(KEY_MAP.keys())

    async def list_apps(self) -> list[dict]:
        return list(COMMON_APPS)

    # --- connection cache plumbing ---
    def _slot(self) -> dict:
        slot = _CONN.get(self.device.id)
        if slot is None:
            slot = _CONN[self.device.id] = {
                "remote": None,
                "last_used": 0.0,
                "lock": asyncio.Lock(),
                "reaper": None,
            }
        return slot

    def _close_slot_conn(self) -> None:
        slot = _CONN.get(self.device.id)
        if not slot:
            return
        remote = slot.get("remote")
        slot["remote"] = None
        if slot.get("reaper"):
            try:
                slot["reaper"].cancel()
            except Exception:
                pass
            slot["reaper"] = None
        if remote is not None:
            try:
                remote.disconnect()
            except Exception:
                pass

    def _schedule_reap(self) -> None:
        slot = self._slot()
        if slot.get("reaper"):
            try:
                slot["reaper"].cancel()
            except Exception:
                pass
        loop = asyncio.get_running_loop()
        dev_id = self.device.id

        def _fire():
            s = _CONN.get(dev_id)
            if not s:
                return
            s["reaper"] = None
            loop.create_task(_reap_locked(dev_id))

        slot["reaper"] = loop.call_later(_CONN_TTL, _fire)

    def _new_remote(self, certfile: str, keyfile: str):
        try:
            from androidtvremote2 import AndroidTVRemote
        except ImportError:
            raise RemoteError("Google TV support library is not installed.", "library_missing")

        return AndroidTVRemote(CLIENT_NAME, certfile, keyfile, self._require_ip())

    async def _connect(self, force: bool = False):
        """Return a live connection, reusing the warm one when possible."""
        slot = self._slot()
        if not force and slot.get("remote") is not None:
            return slot["remote"]

        cert = (self.config or {}).get("cert")
        key = (self.config or {}).get("key")
        if not cert or not key:
            raise RemoteError("Google TV is not paired.", "not_paired")
        certfile, keyfile = _write_cert_files(self.device.id, cert, key)
        remote = self._new_remote(certfile, keyfile)
        try:
            await remote.async_connect()
        except Exception as e:
            name = type(e).__name__
            if "Auth" in name:
                raise RemoteError("Pairing is no longer valid. Re-pair the device.", "not_paired")
            raise RemoteError(f"Could not connect to Google TV: {e}", "unreachable")
        slot["remote"] = remote
        return remote

    async def _run(self, op):
        """Run an operation against a (reused) connection, reconnecting once if
        the warm connection has gone stale."""
        slot = self._slot()
        async with slot["lock"]:
            last_err: Exception | None = None
            for attempt in (1, 2):
                remote = await self._connect(force=(attempt == 2))
                try:
                    result = op(remote)
                except RemoteError:
                    # Connection is healthy — keep it warm, don't leak it.
                    slot["last_used"] = time.monotonic()
                    self._schedule_reap()
                    raise
                except Exception as e:
                    # Warm connection may be dead — drop it and reconnect once.
                    last_err = e
                    self._close_slot_conn()
                    continue
                slot["last_used"] = time.monotonic()
                self._schedule_reap()
                return result
            raise RemoteError(f"Google TV command failed: {last_err}", "error")

    async def status(self) -> RemoteStatus:
        if not self.ip:
            return RemoteStatus(self.protocol, False, False, True, "No IP address configured.")
        paired_creds = bool((self.config or {}).get("cert"))
        # A live, warm connection means the device is reachable and paired.
        slot = _CONN.get(self.device.id)
        if slot and slot.get("remote") is not None:
            return RemoteStatus(self.protocol, True, paired_creds, True,
                                None if paired_creds else "Not paired yet.")
        reachable = await tcp_open(self.ip, CONTROL_PORT, timeout=3) or \
            await tcp_open(self.ip, PAIR_PORT, timeout=3)
        if not reachable:
            return RemoteStatus(self.protocol, False, False, True, "Android TV remote ports not reachable.")
        if not paired_creds:
            return RemoteStatus(self.protocol, True, False, True, "Not paired yet.")
        # Prime a warm connection so the first key press is instant.
        try:
            await self._ensure_connected()
            return RemoteStatus(self.protocol, True, True, True, None)
        except RemoteError as e:
            return RemoteStatus(self.protocol, True, False, True, e.message)

    async def _ensure_connected(self):
        slot = self._slot()
        async with slot["lock"]:
            remote = await self._connect()
            slot["last_used"] = time.monotonic()
            self._schedule_reap()
            return remote

    async def send_key(self, key: str) -> None:
        code = self._map_key(key, KEY_MAP)

        def op(remote):
            remote.send_key_command(code)

        await self._run(op)

    async def launch_app(self, app_id: str) -> None:
        def op(remote):
            remote.send_launch_app_command(app_id)

        await self._run(op)

    async def pair_begin(self) -> PairBeginResult:
        try:
            from androidtvremote2 import AndroidTVRemote
        except ImportError:
            raise RemoteError("Google TV support library is not installed.", "library_missing")

        self._require_ip()
        # Re-pairing invalidates any warm connection.
        self._close_slot_conn()
        if not (await tcp_open(self.ip, PAIR_PORT, timeout=3) or await tcp_open(self.ip, CONTROL_PORT, timeout=3)):
            raise RemoteError("Android TV remote ports not reachable.", "unreachable")
        d = _cert_dir(self.device.id)
        certfile = os.path.join(d, "cert.pem")
        keyfile = os.path.join(d, "key.pem")
        remote = AndroidTVRemote(CLIENT_NAME, certfile, keyfile, self.ip)
        try:
            await remote.async_generate_cert_if_missing()
            await remote.async_start_pairing()
        except Exception as e:
            raise RemoteError(f"Could not start pairing: {e}", "error")
        _PAIR_SESSIONS[self.device.id] = (remote, certfile, keyfile)
        return PairBeginResult(
            requires_pin=True,
            message="Enter the 6-digit code shown on the Google TV screen.",
        )

    async def pair_finish(self, pin) -> dict:
        session = _PAIR_SESSIONS.get(self.device.id)
        if session is None:
            raise RemoteError("No pairing in progress. Start pairing again.", "error")
        remote, certfile, keyfile = session
        if not pin:
            raise RemoteError("A PIN is required.", "error")
        try:
            await remote.async_finish_pairing(pin)
        except Exception as e:
            raise RemoteError(f"Pairing failed — wrong PIN? ({e})", "error")
        finally:
            _PAIR_SESSIONS.pop(self.device.id, None)
        try:
            with open(certfile, "r") as f:
                cert = f.read()
            with open(keyfile, "r") as f:
                key = f.read()
        except Exception as e:
            raise RemoteError(f"Could not read pairing certificate: {e}", "error")
        # New credentials — drop any cached connection so the next action uses them.
        self._close_slot_conn()
        new_config = dict(self.config or {})
        new_config["cert"] = cert
        new_config["key"] = key
        return new_config
