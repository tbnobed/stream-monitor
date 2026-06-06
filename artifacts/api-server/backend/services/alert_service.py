import httpx
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


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

    await _send_email_alert(settings, item_name, item_type, status, reason, incident_id, event)


async def _send_email_alert(
    settings: dict,
    item_name: str,
    item_type: str,
    status: str,
    reason: str,
    incident_id: int,
    event: str,
):
    """Send an incident email via the SendGrid v3 HTTP API.

    Disabled unless the API key + a verified sender (env vars) AND at least one
    recipient (Settings -> alert_email_recipients) are configured. Implemented
    with httpx directly to avoid an extra SDK dependency (same approach as OIDC).
    """
    from config import settings as cfg

    api_key = cfg.sendgrid_api_key
    from_email = cfg.alert_from_email
    if not api_key or not from_email:
        return

    raw = settings.get("alert_email_recipients", "") or ""
    recipients = [
        e.strip()
        for e in raw.replace("\n", ",").replace(";", ",").split(",")
        if e.strip()
    ]
    if not recipients:
        return

    color = "#d32f2f" if status == "DOWN" else "#ed6c02" if status == "WARNING" else "#2e7d32"
    verb = "RESOLVED" if event == "resolved" else status
    timestamp = datetime.utcnow().isoformat()
    subject = f"[OTT Monitor] {item_name} \u2014 {verb}"
    text = (
        f"{item_name} ({item_type})\n"
        f"Status: {status}\n"
        f"Event: {event}\n"
        f"Reason: {reason}\n"
        f"Incident ID: {incident_id}\n"
        f"Time (UTC): {timestamp}\n"
    )
    rows = "".join(
        f'<tr><td style="padding:2px 10px;color:#888">{label}</td>'
        f'<td style="padding:2px 10px">{value}</td></tr>'
        for label, value in (
            ("Status", status),
            ("Event", event),
            ("Reason", reason or "\u2014"),
            ("Incident", f"#{incident_id}"),
            ("Time (UTC)", timestamp),
        )
    )
    html = (
        f'<div style="font-family:system-ui,sans-serif">'
        f'<h2 style="color:{color};margin:0 0 8px">OTT Monitor \u2014 {verb}</h2>'
        f'<p style="margin:0 0 8px"><strong>{item_name}</strong> ({item_type})</p>'
        f'<table style="border-collapse:collapse">{rows}</table>'
        f'</div>'
    )

    payload = {
        "personalizations": [{"to": [{"email": e} for e in recipients]}],
        "from": {"email": from_email, "name": cfg.alert_from_name or "OTT Stream Monitor"},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text},
            {"type": "text/html", "value": html},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code >= 300:
            # Never log the API key; SendGrid echoes errors in the body, not creds.
            logger.warning(
                "SendGrid email alert failed: HTTP %s %s",
                resp.status_code,
                resp.text[:300],
            )
    except Exception as e:
        logger.warning("SendGrid email alert error: %s", e)
