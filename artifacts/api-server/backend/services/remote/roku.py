"""Roku driver — External Control Protocol (ECP) over HTTP, port 8060.

No pairing required. Uses httpx which is already a backend dependency.
Docs: https://developer.roku.com/docs/developer-program/dev-tools/external-control-api.md
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .base import RemoteDriver, RemoteError, RemoteStatus

ECP_PORT = 8060

KEY_MAP = {
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "select": "Select",
    "back": "Back",
    "home": "Home",
    "menu": "Info",
    "play_pause": "Play",
    "rewind": "Rev",
    "forward": "Fwd",
    "volume_up": "VolumeUp",
    "volume_down": "VolumeDown",
    "mute": "VolumeMute",
    "power": "PowerOff",
}


class RokuDriver(RemoteDriver):
    protocol = "ecp"
    requires_pairing = False
    supports_app_launch = True
    keys = list(KEY_MAP.keys())

    def _base_url(self) -> str:
        return f"http://{self._require_ip()}:{ECP_PORT}"

    async def status(self) -> RemoteStatus:
        import httpx

        reachable = False
        detail = None
        if self.ip:
            try:
                async with httpx.AsyncClient(timeout=3) as client:
                    resp = await client.get(f"{self._base_url()}/query/device-info")
                reachable = resp.status_code == 200
                if not reachable:
                    detail = f"Device returned HTTP {resp.status_code}."
            except Exception as e:
                detail = f"Could not reach device: {e}"
        else:
            detail = "No IP address configured."
        return RemoteStatus(
            protocol=self.protocol,
            reachable=reachable,
            paired=reachable,  # ECP needs no pairing
            requires_pairing=False,
            detail=detail,
        )

    async def send_key(self, key: str) -> None:
        import httpx

        code = self._map_key(key, KEY_MAP)
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(f"{self._base_url()}/keypress/{code}")
        except Exception as e:
            raise RemoteError(f"Could not reach Roku: {e}", "unreachable")
        if resp.status_code >= 400:
            raise RemoteError(f"Roku rejected key (HTTP {resp.status_code}).", "error")

    async def launch_app(self, app_id: str) -> None:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(f"{self._base_url()}/launch/{app_id}")
        except Exception as e:
            raise RemoteError(f"Could not reach Roku: {e}", "unreachable")
        if resp.status_code >= 400:
            raise RemoteError(f"Roku could not launch app (HTTP {resp.status_code}).", "error")

    async def list_apps(self) -> list[dict]:
        import httpx

        if not self.ip:
            return []
        try:
            async with httpx.AsyncClient(timeout=4) as client:
                resp = await client.get(f"{self._base_url()}/query/apps")
            if resp.status_code != 200:
                return []
            root = ET.fromstring(resp.text)
            apps = []
            for app in root.findall("app"):
                app_id = app.get("id")
                name = (app.text or "").strip()
                if app_id and name:
                    apps.append({"id": app_id, "name": name})
            return apps
        except Exception:
            return []
