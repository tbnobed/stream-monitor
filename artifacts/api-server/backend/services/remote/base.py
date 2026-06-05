"""Base interface and shared helpers for native OTT remote-control drivers.

Each driver talks directly to a device on the local LAN using that platform's
native protocol. Drivers lazily import their heavy third-party library *inside*
methods, so a missing/broken library only disables that one platform instead of
crashing the whole backend.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

# Canonical logical keys the UI may send. Each driver maps the subset it supports
# to its own protocol-specific codes.
STANDARD_KEYS = [
    "up", "down", "left", "right", "select",
    "back", "home", "menu",
    "play_pause", "rewind", "forward",
    "volume_up", "volume_down", "mute",
    "power",
]


class RemoteError(Exception):
    """Expected, user-facing remote failure (never an unhandled 500).

    code is one of: unreachable, not_paired, unsupported, library_missing, error
    """

    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass
class RemoteCapabilities:
    protocol: str
    requires_pairing: bool = False
    supports_app_launch: bool = False
    keys: list[str] = field(default_factory=list)
    apps: list[dict] = field(default_factory=list)


@dataclass
class RemoteStatus:
    protocol: str
    reachable: bool
    paired: bool
    requires_pairing: bool
    detail: Optional[str] = None


@dataclass
class PairBeginResult:
    requires_pin: bool
    message: str
    # If set, persist immediately to device.remote_config (used by ADB which has
    # no PIN step and needs its generated key stored before verification).
    config: Optional[dict] = None


async def tcp_open(ip: str, port: int, timeout: float = 3.0) -> bool:
    """Return True if a TCP connection to ip:port can be opened quickly."""
    if not ip:
        return False
    try:
        fut = asyncio.open_connection(ip, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


class RemoteDriver:
    """Abstract base. Subclasses set class attrs and implement async methods."""

    protocol: str = "none"
    requires_pairing: bool = False
    supports_app_launch: bool = False
    keys: list[str] = []

    def __init__(self, device):
        self.device = device
        self.ip = (getattr(device, "ip_address", None) or "").strip()
        self.config = getattr(device, "remote_config", None) or {}

    # --- introspection (no network) ---
    def is_paired(self) -> bool:
        """Whether the device is ready to control without further pairing."""
        if not self.requires_pairing:
            return bool(self.ip)
        return bool(self.config)

    def capabilities(self) -> RemoteCapabilities:
        return RemoteCapabilities(
            protocol=self.protocol,
            requires_pairing=self.requires_pairing,
            supports_app_launch=self.supports_app_launch,
            keys=list(self.keys),
            apps=[],
        )

    async def list_apps(self) -> list[dict]:
        return []

    # --- operations (network) ---
    async def status(self) -> RemoteStatus:
        raise NotImplementedError

    async def send_key(self, key: str) -> None:
        raise NotImplementedError

    async def launch_app(self, app_id: str) -> None:
        raise RemoteError("App launch is not supported for this device.", "unsupported")

    async def pair_begin(self) -> PairBeginResult:
        raise RemoteError("This device does not require pairing.", "unsupported")

    async def pair_finish(self, pin: Optional[str]) -> dict:
        raise RemoteError("This device does not require pairing.", "unsupported")

    def _require_ip(self) -> str:
        if not self.ip:
            raise RemoteError("No IP address configured for this device.", "error")
        return self.ip

    def _map_key(self, key: str, mapping: dict) -> str:
        code = mapping.get(key)
        if code is None:
            raise RemoteError(f"Key '{key}' is not supported on this device.", "unsupported")
        return code
