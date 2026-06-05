"""Fire TV driver — ADB over TCP, port 5555.

Authorization model: ADB uses an RSA key; the first connection makes the device
show an "Allow USB debugging?" dialog with the host key's fingerprint. There is
no PIN. We generate an RSA key during pair_begin (persisted immediately) and
verify the device accepted it during pair_finish.
"""
from __future__ import annotations

import asyncio
import os
import tempfile

from .base import RemoteDriver, RemoteError, RemoteStatus, PairBeginResult, tcp_open

ADB_PORT = 5555

# Android keycodes -> `input keyevent N`
KEY_MAP = {
    "up": 19,
    "down": 20,
    "left": 21,
    "right": 22,
    "select": 23,
    "back": 4,
    "home": 3,
    "menu": 82,
    "play_pause": 85,
    "rewind": 89,
    "forward": 90,
    "volume_up": 24,
    "volume_down": 25,
    "mute": 164,
    "power": 26,
}

COMMON_APPS = [
    {"id": "com.netflix.ninja", "name": "Netflix"},
    {"id": "com.amazon.firetv.youtube", "name": "YouTube"},
    {"id": "com.amazon.avod", "name": "Prime Video"},
    {"id": "com.disney.disneyplus", "name": "Disney+"},
]


def _new_keypair() -> dict:
    """Generate an ADB RSA keypair and return {'priv': ..., 'pub': ...} as text."""
    from adb_shell.auth.keygen import keygen

    tmpdir = tempfile.mkdtemp(prefix="adbkey_")
    priv_path = os.path.join(tmpdir, "adbkey")
    keygen(priv_path)
    with open(priv_path, "r") as f:
        priv = f.read()
    with open(priv_path + ".pub", "r") as f:
        pub = f.read()
    return {"priv": priv, "pub": pub}


class FireTVDriver(RemoteDriver):
    protocol = "adb"
    requires_pairing = True
    supports_app_launch = True
    keys = list(KEY_MAP.keys())

    async def list_apps(self) -> list[dict]:
        return list(COMMON_APPS)

    def _signer(self):
        try:
            from adb_shell.auth.sign_pythonrsa import PythonRSASigner
        except ImportError:
            raise RemoteError("Fire TV support library is not installed.", "library_missing")

        priv = self.config.get("priv")
        pub = self.config.get("pub")
        if not priv:
            raise RemoteError("Device is not paired (no ADB key).", "not_paired")
        return PythonRSASigner(pub or "", priv)

    async def _connect(self, timeout: float = 6.0):
        try:
            from adb_shell.adb_device_async import AdbDeviceTcpAsync
        except ImportError:
            raise RemoteError("Fire TV support library is not installed.", "library_missing")

        ip = self._require_ip()
        signer = self._signer()
        dev = AdbDeviceTcpAsync(ip, ADB_PORT, default_transport_timeout_s=timeout)
        try:
            await dev.connect(rsa_keys=[signer], auth_timeout_s=timeout)
        except Exception as e:
            name = type(e).__name__
            if "Auth" in name:
                raise RemoteError(
                    "Device has not authorized this app. Accept the debugging prompt on the TV.",
                    "not_paired",
                )
            raise RemoteError(f"Could not connect to Fire TV: {e}", "unreachable")
        return dev

    async def status(self) -> RemoteStatus:
        if not self.ip:
            return RemoteStatus(self.protocol, False, False, True, "No IP address configured.")
        reachable = await tcp_open(self.ip, ADB_PORT, timeout=3)
        if not reachable:
            return RemoteStatus(self.protocol, False, False, True, "ADB port 5555 is not reachable.")
        if not self.config.get("priv"):
            return RemoteStatus(self.protocol, True, False, True, "Not paired yet.")
        try:
            dev = await self._connect()
            await dev.close()
            return RemoteStatus(self.protocol, True, True, True, None)
        except RemoteError as e:
            return RemoteStatus(self.protocol, True, False, True, e.message)

    async def send_key(self, key: str) -> None:
        code = self._map_key(key, KEY_MAP)
        dev = await self._connect()
        try:
            await dev.shell(f"input keyevent {code}")
        except Exception as e:
            raise RemoteError(f"Fire TV command failed: {e}", "error")
        finally:
            await dev.close()

    async def launch_app(self, app_id: str) -> None:
        dev = await self._connect()
        try:
            await dev.shell(f"monkey -p {app_id} -c android.intent.category.LAUNCHER 1")
        except Exception as e:
            raise RemoteError(f"Fire TV app launch failed: {e}", "error")
        finally:
            await dev.close()

    async def pair_begin(self) -> PairBeginResult:
        self._require_ip()
        if not await tcp_open(self.ip, ADB_PORT, timeout=3):
            raise RemoteError(
                "ADB port 5555 is not reachable. Enable ADB debugging / Apps from Unknown Sources on the Fire TV.",
                "unreachable",
            )
        keys = self.config.get("priv") and self.config or _new_keypair()
        # Trigger the authorization dialog by attempting a connection (best-effort).
        try:
            from adb_shell.adb_device_async import AdbDeviceTcpAsync
            from adb_shell.auth.sign_pythonrsa import PythonRSASigner

            signer = PythonRSASigner(keys.get("pub", ""), keys["priv"])
            dev = AdbDeviceTcpAsync(self.ip, ADB_PORT, default_transport_timeout_s=4)
            try:
                await asyncio.wait_for(dev.connect(rsa_keys=[signer], auth_timeout_s=1), timeout=5)
                await dev.close()
            except Exception:
                pass
        except ImportError:
            raise RemoteError("Fire TV support library is not installed.", "library_missing")
        return PairBeginResult(
            requires_pin=False,
            message="Accept the 'Allow debugging?' prompt on the Fire TV, then click Verify.",
            config=keys,
        )

    async def pair_finish(self, pin) -> dict:
        # No PIN; verify the device accepted our key.
        dev = await self._connect()
        await dev.close()
        return self.config
