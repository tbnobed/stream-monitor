"""Apple TV driver — pyatv (Companion protocol), PIN pairing.

Companion gives both remote control (D-pad/menu/home) and app launch on modern
tvOS. Credentials are obtained via PIN pairing and stored in remote_config.

Performance note: a cold Apple TV action is slow because it requires an mDNS
scan to (re)discover the device followed by an encrypted Companion handshake.
To avoid paying that on every key press, we cache the discovered config per
device for a short TTL and keep the Companion connection open between actions,
closing it after an idle period. The first press still pays the cost (and a
sleeping Apple TV must wake first), but subsequent presses reuse the warm
connection.
"""
from __future__ import annotations

import asyncio
import time

from .base import RemoteDriver, RemoteError, RemoteStatus, PairBeginResult

# In-memory pairing sessions, keyed by device id, held between begin and finish.
_PAIR_SESSIONS: dict = {}

# In-memory connection cache, keyed by device id. Each slot keeps the live pyatv
# connection, the discovered config (with its timestamp), a per-device lock to
# serialize access, and the idle-reaper timer handle.
_CONN: dict = {}

# How long a discovered device config is reused before re-scanning (seconds).
_SCAN_TTL = 60.0
# How long a Companion connection is kept open after its last use (seconds).
_CONN_TTL = 120.0

KEYS = [
    "up", "down", "left", "right", "select",
    "back", "home", "menu", "play_pause",
    "volume_up", "volume_down",
]

# logical key -> pyatv RemoteControl method name
RC_METHODS = {
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "select": "select",
    "menu": "menu",
    "back": "menu",
    "home": "home",
    "play_pause": "play_pause",
}
AUDIO_METHODS = {
    "volume_up": "volume_up",
    "volume_down": "volume_down",
}


async def _reap_locked(dev_id) -> None:
    """Close an idle Companion connection under the per-device lock.

    Runs only when the idle timer fires. Acquiring the lock guarantees no
    operation is in flight, and the last_used re-check avoids closing a
    connection that was warmed again while this task waited for the lock.
    """
    slot = _CONN.get(dev_id)
    if not slot:
        return
    async with slot["lock"]:
        atv = slot.get("atv")
        if atv is None:
            return
        if (time.monotonic() - slot.get("last_used", 0.0)) < _CONN_TTL:
            return
        slot["atv"] = None
        try:
            atv.close()
        except Exception:
            pass


class AppleTVDriver(RemoteDriver):
    protocol = "companion"
    requires_pairing = True
    supports_app_launch = True
    keys = KEYS

    # --- connection cache plumbing ---
    def _slot(self) -> dict:
        slot = _CONN.get(self.device.id)
        if slot is None:
            slot = _CONN[self.device.id] = {
                "atv": None,
                "conf": None,
                "conf_ts": 0.0,
                "last_used": 0.0,
                "lock": asyncio.Lock(),
                "reaper": None,
            }
        return slot

    def _close_slot_conn(self) -> None:
        slot = _CONN.get(self.device.id)
        if not slot:
            return
        atv = slot.get("atv")
        slot["atv"] = None
        if slot.get("reaper"):
            try:
                slot["reaper"].cancel()
            except Exception:
                pass
            slot["reaper"] = None
        if atv is not None:
            try:
                atv.close()
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
            # Close under the per-device lock so we never tear a connection down
            # mid-operation; the coroutine also re-checks idleness before closing.
            loop.create_task(_reap_locked(dev_id))

        slot["reaper"] = loop.call_later(_CONN_TTL, _fire)

    async def _scan_conf(self, timeout: float = 5.0):
        try:
            import pyatv
        except ImportError:
            raise RemoteError("Apple TV support library is not installed.", "library_missing")

        loop = asyncio.get_running_loop()
        atvs = await pyatv.scan(loop, hosts=[self._require_ip()], timeout=timeout)
        if not atvs:
            raise RemoteError("Apple TV not found on the network.", "unreachable")
        return atvs[0]

    async def _get_conf(self, force: bool = False):
        """Return a discovered config, reusing a recent scan when possible."""
        slot = self._slot()
        now = time.monotonic()
        if (
            not force
            and slot.get("conf") is not None
            and (now - slot.get("conf_ts", 0.0)) < _SCAN_TTL
        ):
            return slot["conf"]
        conf = await self._scan_conf()
        slot["conf"] = conf
        slot["conf_ts"] = now
        return conf

    async def _connect(self, force: bool = False):
        """Return a live pyatv connection, reusing the cached one when possible."""
        slot = self._slot()
        if not force and slot.get("atv") is not None:
            return slot["atv"]

        import pyatv
        from pyatv.const import Protocol

        creds = (self.config or {}).get("credentials") or {}
        if not creds:
            raise RemoteError("Apple TV is not paired.", "not_paired")

        conf = await self._get_conf(force=force)
        for proto_name, cred in creds.items():
            try:
                conf.set_credentials(Protocol[proto_name], cred)
            except Exception:
                pass

        loop = asyncio.get_running_loop()
        try:
            atv = await pyatv.connect(conf, loop)
        except Exception as e:
            # A cached config may be stale (device moved/IP changed) — drop it so
            # the next attempt re-scans.
            slot["conf"] = None
            raise RemoteError(f"Could not connect to Apple TV: {e}", "error")
        slot["atv"] = atv
        return atv

    async def _run(self, op):
        """Run an operation against a (reused) connection, reconnecting once if
        the warm connection has gone stale."""
        slot = self._slot()
        async with slot["lock"]:
            last_err: Exception | None = None
            for attempt in (1, 2):
                atv = await self._connect(force=(attempt == 2))
                try:
                    result = await op(atv)
                except RemoteError:
                    # Connection is healthy (e.g. unsupported key) — keep it warm
                    # and reschedule the idle reaper so it is not leaked.
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
            raise RemoteError(f"Apple TV command failed: {last_err}", "error")

    async def status(self) -> RemoteStatus:
        if not self.ip:
            return RemoteStatus(self.protocol, False, False, True, "No IP address configured.")
        paired = bool((self.config or {}).get("credentials"))
        # A live, warm connection means the device is reachable — no scan needed.
        slot = _CONN.get(self.device.id)
        if slot and slot.get("atv") is not None:
            return RemoteStatus(self.protocol, True, paired, True,
                                None if paired else "Not paired yet.")
        try:
            await self._get_conf()
            reachable = True
        except RemoteError as e:
            return RemoteStatus(self.protocol, False, paired, True, e.message)
        except ImportError:
            return RemoteStatus(self.protocol, False, False, True, "Apple TV library not installed.")
        return RemoteStatus(self.protocol, reachable, paired, True,
                            None if paired else "Not paired yet.")

    async def send_key(self, key: str) -> None:
        async def op(atv):
            if key in RC_METHODS:
                await getattr(atv.remote_control, RC_METHODS[key])()
            elif key in AUDIO_METHODS:
                await getattr(atv.audio, AUDIO_METHODS[key])()
            else:
                raise RemoteError(f"Key '{key}' is not supported on Apple TV.", "unsupported")

        await self._run(op)

    async def launch_app(self, app_id: str) -> None:
        async def op(atv):
            await atv.apps.launch_app(app_id)

        await self._run(op)

    async def list_apps(self) -> list[dict]:
        async def op(atv):
            apps = await atv.apps.app_list()
            return [{"id": a.identifier, "name": a.name} for a in apps if a.identifier]

        try:
            return await self._run(op)
        except RemoteError:
            return []

    async def pair_begin(self) -> PairBeginResult:
        # Re-pairing invalidates any warm connection/credentials.
        self._close_slot_conn()
        conf = await self._scan_conf()
        try:
            import pyatv
            from pyatv.const import Protocol
        except ImportError:
            raise RemoteError("Apple TV support library is not installed.", "library_missing")

        loop = asyncio.get_running_loop()
        try:
            pairing = await pyatv.pair(conf, Protocol.Companion, loop)
            await pairing.begin()
        except Exception as e:
            raise RemoteError(f"Could not start pairing: {e}", "error")
        _PAIR_SESSIONS[self.device.id] = pairing
        return PairBeginResult(
            requires_pin=True,
            message="Enter the 4-digit PIN shown on the Apple TV screen.",
        )

    async def pair_finish(self, pin) -> dict:
        pairing = _PAIR_SESSIONS.get(self.device.id)
        if pairing is None:
            raise RemoteError("No pairing in progress. Start pairing again.", "error")
        if not pin:
            raise RemoteError("A PIN is required.", "error")
        try:
            pairing.pin(pin)
            await pairing.finish()
            if not pairing.has_paired:
                raise RemoteError("Pairing failed — wrong PIN?", "error")
            cred = pairing.service.credentials
        except RemoteError:
            raise
        except Exception as e:
            raise RemoteError(f"Pairing failed: {e}", "error")
        finally:
            try:
                await pairing.close()
            except Exception:
                pass
            _PAIR_SESSIONS.pop(self.device.id, None)
        # New credentials — drop any cached connection so the next action uses them.
        self._close_slot_conn()
        new_config = dict(self.config or {})
        creds = dict(new_config.get("credentials") or {})
        creds["Companion"] = cred
        new_config["credentials"] = creds
        return new_config
