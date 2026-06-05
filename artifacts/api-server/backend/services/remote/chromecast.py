"""Chromecast / Google TV driver — androidtvremote2, PIN pairing.

Modern Chromecast-with-Google-TV devices speak the Android TV remote protocol
(ports 6466/6467), which provides a full D-pad plus app launch via deep links.
Pairing uses a TLS client cert; the device shows a 6-digit PIN on screen.

Note: legacy Chromecast dongles (no on-screen UI) cannot be D-pad controlled and
are not supported by this driver.
"""
from __future__ import annotations

import os
import tempfile

from .base import RemoteDriver, RemoteError, RemoteStatus, PairBeginResult, tcp_open

PAIR_PORT = 6467
CONTROL_PORT = 6466
CLIENT_NAME = "OTT NOC Monitor"

# In-memory pairing sessions keyed by device id (remote + cert/key file paths).
_PAIR_SESSIONS: dict = {}

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


class GoogleTVDriver(RemoteDriver):
    protocol = "androidtv"
    requires_pairing = True
    supports_app_launch = True
    keys = list(KEY_MAP.keys())

    async def list_apps(self) -> list[dict]:
        return list(COMMON_APPS)

    def _new_remote(self, certfile: str, keyfile: str):
        try:
            from androidtvremote2 import AndroidTVRemote
        except ImportError:
            raise RemoteError("Google TV support library is not installed.", "library_missing")

        return AndroidTVRemote(CLIENT_NAME, certfile, keyfile, self._require_ip())

    async def _connected_remote(self):
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
        return remote

    async def status(self) -> RemoteStatus:
        if not self.ip:
            return RemoteStatus(self.protocol, False, False, True, "No IP address configured.")
        reachable = await tcp_open(self.ip, CONTROL_PORT, timeout=3) or \
            await tcp_open(self.ip, PAIR_PORT, timeout=3)
        if not reachable:
            return RemoteStatus(self.protocol, False, False, True, "Android TV remote ports not reachable.")
        if not (self.config or {}).get("cert"):
            return RemoteStatus(self.protocol, True, False, True, "Not paired yet.")
        try:
            remote = await self._connected_remote()
            remote.disconnect()
            return RemoteStatus(self.protocol, True, True, True, None)
        except RemoteError as e:
            return RemoteStatus(self.protocol, True, False, True, e.message)

    async def send_key(self, key: str) -> None:
        code = self._map_key(key, KEY_MAP)
        remote = await self._connected_remote()
        try:
            remote.send_key_command(code)
        except Exception as e:
            raise RemoteError(f"Google TV command failed: {e}", "error")
        finally:
            remote.disconnect()

    async def launch_app(self, app_id: str) -> None:
        remote = await self._connected_remote()
        try:
            remote.send_launch_app_command(app_id)
        except Exception as e:
            raise RemoteError(f"Google TV app launch failed: {e}", "error")
        finally:
            remote.disconnect()

    async def pair_begin(self) -> PairBeginResult:
        try:
            from androidtvremote2 import AndroidTVRemote
        except ImportError:
            raise RemoteError("Google TV support library is not installed.", "library_missing")

        self._require_ip()
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
        new_config = dict(self.config or {})
        new_config["cert"] = cert
        new_config["key"] = key
        return new_config
