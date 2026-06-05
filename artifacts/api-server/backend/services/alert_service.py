import httpx
import json
import os
from datetime import datetime


async def get_webhook_settings():
    """Read webhook settings from DB."""
    try:
        from database import SessionLocal
        from models import Setting
        db = SessionLocal()
        settings = {s.key: s.value for s in db.query(Setting).all()}
        db.close()
        return settings
    except Exception:
        return {}


async def send_alert(
    item_type: str,
    item_id: int,
    item_name: str,
    status: str,
    reason: str,
    incident_id: int,
    event: str,  # "opened" or "resolved"
):
    settings = await get_webhook_settings()

    if settings.get("alerts_enabled", "true").lower() != "true":
        return

    # Skip WARNING alerts unless configured to alert on them
    if status == "WARNING" and settings.get("alert_on_warning", "false").lower() != "true":
        return

    payload = {
        "event": event,
        "item_name": item_name,
        "item_type": item_type,
        "status": status,
        "reason": reason,
        "incident_id": incident_id,
        "timestamp": datetime.utcnow().isoformat(),
    }

    urls = []

    slack_url = settings.get("slack_webhook_url", "")
    if slack_url:
        slack_payload = {
            "text": f"*OTT Monitor Alert* [{event.upper()}]\n*{item_name}* ({item_type}) — {status}\n_{reason}_",
            "attachments": [{
                "color": "#ff0000" if status == "DOWN" else "#ffa500" if status == "WARNING" else "#00ff00",
                "fields": [
                    {"title": "Status", "value": status, "short": True},
                    {"title": "Reason", "value": reason, "short": True},
                    {"title": "Incident ID", "value": str(incident_id), "short": True},
                ],
            }],
        }
        urls.append((slack_url, slack_payload))

    discord_url = settings.get("discord_webhook_url", "")
    if discord_url:
        color = 0xFF0000 if status == "DOWN" else 0xFFA500 if status == "WARNING" else 0x00FF00
        discord_payload = {
            "embeds": [{
                "title": f"OTT Monitor Alert [{event.upper()}]",
                "description": f"**{item_name}** ({item_type}) — {status}\n{reason}",
                "color": color,
                "timestamp": datetime.utcnow().isoformat(),
            }],
        }
        urls.append((discord_url, discord_payload))

    generic_url = settings.get("generic_webhook_url", "")
    if generic_url:
        urls.append((generic_url, payload))

    async with httpx.AsyncClient(timeout=10) as client:
        for url, body in urls:
            try:
                await client.post(url, json=body)
            except Exception:
                pass
