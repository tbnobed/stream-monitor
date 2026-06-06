"""Fire TV driver — ADB over TCP, port 5555.

Authorization model: ADB uses an RSA key; the first connection makes the device
show an "Allow USB debugging?" dialog with the host key's fingerprint. There is
no PIN. We generate an RSA key during pair_begin (persisted immediately) and
verify the device accepted it during pair_finish.

Performance note: opening an ADB connection performs an RSA auth handshake that
is slow (often seconds). Reconnecting on every key press is the latency culprit,
so we keep the connection warm between actions and close it after an idle period,
mirroring the Apple TV / Google TV drivers. Only the first action pays the
connect cost. Unlike androidtvremote2, adb_shell's connect/close are async.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time

from .base import RemoteDriver, RemoteError, RemoteStatus, PairBeginResult, tcp_open

logger = logging.getLogger(__name__)

ADB_PORT = 5555

# In-memory connection cache keyed by device id: live ADB device, per-device
# lock, last-used timestamp, and the idle-reaper timer handle.
_CONN: dict = {}

# How long a connection is kept open after its last use (seconds).
_CONN_TTL = 300.0

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
        dev = slot.get("remote")
        if dev is None:
            return
        if (time.monotonic() - slot.get("last_used", 0.0)) < _CONN_TTL:
            return
        slot["remote"] = None
        try:
            await dev.close()
        except Exception:
            pass


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

    async def _close_slot_conn_locked(self) -> None:
        """Drop and close the cached connection. Caller MUST hold slot['lock'].

        close() is async (it yields), so teardown must be serialized under the
        per-device lock or it can race an in-flight op / a just-established
        connection. Used from within _run, which already holds the lock.
        """
        slot = _CONN.get(self.device.id)
        if not slot:
            return
        dev = slot.get("remote")
        slot["remote"] = None
        if slot.get("reaper"):
            try:
                slot["reaper"].cancel()
            except Exception:
                pass
            slot["reaper"] = None
        if dev is not None:
            try:
                await dev.close()
            except Exception:
                pass

    async def _close_slot_conn(self) -> None:
        """Lock-acquiring teardown for external callers (e.g. pairing)."""
        slot = self._slot()
        async with slot["lock"]:
            await self._close_slot_conn_locked()

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

    async def _connect(self, force: bool = False, timeout: float = 6.0):
        """Return a live ADB connection, reusing the warm one when possible."""
        slot = self._slot()
        if not force and slot.get("remote") is not None:
            return slot["remote"]

        try:
            from adb_shell.adb_device_async import AdbDeviceTcpAsync
        except ImportError:
            raise RemoteError("Fire TV support library is not installed.", "library_missing")

        ip = self._require_ip()
        signer = self._signer()
        dev = AdbDeviceTcpAsync(ip, ADB_PORT, default_transport_timeout_s=timeout)
        t0 = time.monotonic()
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
        logger.info(
            "firetv connect device=%s ip=%s handshake=%.3fs",
            self.device.id, ip, time.monotonic() - t0,
        )
        slot["remote"] = dev
        return dev

    async def _run(self, op):
        """Run an async operation against a (reused) connection, reconnecting
        once if the warm connection has gone stale."""
        slot = self._slot()
        async with slot["lock"]:
            last_err: Exception | None = None
            for attempt in (1, 2):
                reused = not (attempt == 2) and slot.get("remote") is not None
                t_conn = time.monotonic()
                dev = await self._connect(force=(attempt == 2))
                t_op = time.monotonic()
                try:
                    result = await op(dev)
                except RemoteError:
                    # Connection is healthy — keep it warm, don't leak it.
                    slot["last_used"] = time.monotonic()
                    self._schedule_reap()
                    raise
                except Exception as e:
                    # Warm connection may be dead — drop it and reconnect once.
                    # We already hold the lock here, so use the locked variant.
                    last_err = e
                    logger.warning(
                        "firetv op failed device=%s attempt=%d reused=%s: %s: %s",
                        self.device.id, attempt, reused, type(e).__name__, e,
                    )
                    await self._close_slot_conn_locked()
                    continue
                done = time.monotonic()
                logger.info(
                    "firetv send device=%s reused=%s connect=%.3fs op=%.3fs total=%.3fs",
                    self.device.id, reused, t_op - t_conn, done - t_op, done - t_conn,
                )
                slot["last_used"] = time.monotonic()
                self._schedule_reap()
                return result
            raise RemoteError(f"Fire TV command failed: {last_err}", "error")

    async def _ensure_connected(self):
        slot = self._slot()
        async with slot["lock"]:
            dev = await self._connect()
            slot["last_used"] = time.monotonic()
            self._schedule_reap()
            return dev

    async def status(self) -> RemoteStatus:
        if not self.ip:
            return RemoteStatus(self.protocol, False, False, True, "No IP address configured.")
        paired_creds = bool(self.config.get("priv"))
        # A live, warm connection means the device is reachable and paired.
        slot = _CONN.get(self.device.id)
        if slot and slot.get("remote") is not None:
            return RemoteStatus(self.protocol, True, paired_creds, True,
                                None if paired_creds else "Not paired yet.")
        reachable = await tcp_open(self.ip, ADB_PORT, timeout=3)
        if not reachable:
            return RemoteStatus(self.protocol, False, False, True, "ADB port 5555 is not reachable.")
        if not paired_creds:
            return RemoteStatus(self.protocol, True, False, True, "Not paired yet.")
        # Prime a warm connection so the first key press is instant.
        try:
            await self._ensure_connected()
            return RemoteStatus(self.protocol, True, True, True, None)
        except RemoteError as e:
            return RemoteStatus(self.protocol, True, False, True, e.message)

    async def send_key(self, key: str) -> None:
        code = self._map_key(key, KEY_MAP)

        async def op(dev):
            await dev.shell(f"input keyevent {code}")

        await self._run(op)

    async def launch_app(self, app_id: str) -> None:
        async def op(dev):
            await dev.shell(f"monkey -p {app_id} -c android.intent.category.LAUNCHER 1")

        await self._run(op)

    async def pair_begin(self) -> PairBeginResult:
        self._require_ip()
        # Re-pairing invalidates any warm connection.
        await self._close_slot_conn()
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
        # No PIN; verify the device accepted our key (and keep the connection warm).
        await self._close_slot_conn()
        await self._ensure_connected()
        return self.config
