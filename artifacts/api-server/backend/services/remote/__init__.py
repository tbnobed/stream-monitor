"""Native OTT remote-control driver registry.

Exposes get_driver() to build the right driver for a device, and remote_info()
for cheap (no-network) metadata used to enrich DeviceOut without ever leaking
raw credentials.
"""
from __future__ import annotations

from typing import Optional

from .base import RemoteDriver, RemoteError, RemoteStatus, RemoteCapabilities, PairBeginResult
from .roku import RokuDriver
from .firetv import FireTVDriver
from .appletv import AppleTVDriver
from .chromecast import GoogleTVDriver

_DRIVERS = {
    "roku": RokuDriver,
    "firetv": FireTVDriver,
    "appletv": AppleTVDriver,
    "chromecast": GoogleTVDriver,
}


def get_driver(device) -> Optional[RemoteDriver]:
    cls = _DRIVERS.get(getattr(device, "platform", None))
    if cls is None:
        return None
    return cls(device)


def remote_info(device) -> dict:
    """Cheap metadata (no network) for DeviceOut enrichment."""
    driver = get_driver(device)
    if driver is None:
        return {
            "protocol": None,
            "capable": False,
            "requires_pairing": False,
            "paired": False,
        }
    return {
        "protocol": driver.protocol,
        "capable": True,
        "requires_pairing": driver.requires_pairing,
        "paired": driver.is_paired(),
    }


__all__ = [
    "RemoteDriver",
    "RemoteError",
    "RemoteStatus",
    "RemoteCapabilities",
    "PairBeginResult",
    "get_driver",
    "remote_info",
]
