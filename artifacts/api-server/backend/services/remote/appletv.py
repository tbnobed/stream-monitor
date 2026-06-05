"""Apple TV driver — pyatv (Companion protocol), PIN pairing.

Companion gives both remote control (D-pad/menu/home) and app launch on modern
tvOS. Credentials are obtained via PIN pairing and stored in remote_config.
"""
from __future__ import annotations

import asyncio

from .base import RemoteDriver, RemoteError, RemoteStatus, PairBeginResult

# In-memory pairing sessions, keyed by device id, held between begin and finish.
_PAIR_SESSIONS: dict = {}

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


class AppleTVDriver(RemoteDriver):
    protocol = "companion"
    requires_pairing = True
    supports_app_launch = True
    keys = KEYS

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

    async def _connect(self):
        import pyatv
        from pyatv.const import Protocol

        creds = (self.config or {}).get("credentials") or {}
        if not creds:
            raise RemoteError("Apple TV is not paired.", "not_paired")
        conf = await self._scan_conf()
        for proto_name, cred in creds.items():
            try:
                conf.set_credentials(Protocol[proto_name], cred)
            except Exception:
                pass
        loop = asyncio.get_running_loop()
        try:
            atv = await pyatv.connect(conf, loop)
        except Exception as e:
            raise RemoteError(f"Could not connect to Apple TV: {e}", "error")
        return atv

    async def status(self) -> RemoteStatus:
        if not self.ip:
            return RemoteStatus(self.protocol, False, False, True, "No IP address configured.")
        try:
            await self._scan_conf()
            reachable = True
        except RemoteError as e:
            return RemoteStatus(self.protocol, False, False, True, e.message)
        except ImportError:
            return RemoteStatus(self.protocol, False, False, True, "Apple TV library not installed.")
        paired = bool((self.config or {}).get("credentials"))
        return RemoteStatus(self.protocol, reachable, paired, True,
                            None if paired else "Not paired yet.")

    async def send_key(self, key: str) -> None:
        atv = await self._connect()
        try:
            if key in RC_METHODS:
                await getattr(atv.remote_control, RC_METHODS[key])()
            elif key in AUDIO_METHODS:
                await getattr(atv.audio, AUDIO_METHODS[key])()
            else:
                raise RemoteError(f"Key '{key}' is not supported on Apple TV.", "unsupported")
        except RemoteError:
            raise
        except Exception as e:
            raise RemoteError(f"Apple TV command failed: {e}", "error")
        finally:
            atv.close()

    async def launch_app(self, app_id: str) -> None:
        atv = await self._connect()
        try:
            await atv.apps.launch_app(app_id)
        except Exception as e:
            raise RemoteError(f"Apple TV app launch failed: {e}", "error")
        finally:
            atv.close()

    async def list_apps(self) -> list[dict]:
        try:
            atv = await self._connect()
        except RemoteError:
            return []
        try:
            apps = await atv.apps.app_list()
            return [{"id": a.identifier, "name": a.name} for a in apps if a.identifier]
        except Exception:
            return []
        finally:
            atv.close()

    async def pair_begin(self) -> PairBeginResult:
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
        new_config = dict(self.config or {})
        creds = dict(new_config.get("credentials") or {})
        creds["Companion"] = cred
        new_config["credentials"] = creds
        return new_config
