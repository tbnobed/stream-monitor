from datetime import datetime
from sqlalchemy.orm import Session
from models import Device, HlsStream, Incident, CheckResult
from sse_manager import sse_manager
import asyncio


async def handle_status_change(
    db: Session,
    item_type: str,
    item_id: int,
    new_status: str,
    reason: str,
    detail: dict = None,
    frame_thumbnail_path: str = None,
):
    """Core debounce + incident logic shared by both workers."""
    if item_type == "device":
        item = db.query(Device).filter(Device.id == item_id).first()
    else:
        item = db.query(HlsStream).filter(HlsStream.id == item_id).first()

    if not item:
        return

    # Store check result
    cr = CheckResult(
        device_id=item_id if item_type == "device" else None,
        hls_stream_id=item_id if item_type == "hls_stream" else None,
        status=new_status,
        detail=detail or {},
        frame_thumbnail_path=frame_thumbnail_path,
        timestamp=datetime.utcnow(),
    )
    db.add(cr)

    # Debounce logic
    if item.pending_status == new_status:
        item.consecutive_status_count += 1
    else:
        item.pending_status = new_status
        item.consecutive_status_count = 1

    item.last_checked_at = datetime.utcnow()

    debounce_count = 2
    try:
        from models import Setting
        setting = db.query(Setting).filter(Setting.key == "debounce_count").first()
        if setting:
            debounce_count = int(setting.value)
    except Exception:
        pass

    # Only update official status after debounce threshold
    if item.consecutive_status_count >= debounce_count:
        old_status = item.current_status
        if old_status != new_status:
            item.current_status = new_status
            item.failure_reason = reason if new_status in ("DOWN", "WARNING") else None

            # Incident management
            await _manage_incident(db, item_type, item_id, item.name, old_status, new_status, reason)

            # SSE broadcast
            asyncio.create_task(sse_manager.broadcast("status_change", {
                "item_type": item_type,
                "item_id": item_id,
                "item_name": item.name,
                "old_status": old_status,
                "new_status": new_status,
                "reason": reason,
            }))

    db.commit()


async def _manage_incident(
    db: Session,
    item_type: str,
    item_id: int,
    item_name: str,
    old_status: str,
    new_status: str,
    reason: str,
):
    is_bad = new_status in ("DOWN", "WARNING")
    was_bad = old_status in ("DOWN", "WARNING")

    filter_kwargs = {"device_id": item_id} if item_type == "device" else {"hls_stream_id": item_id}

    if is_bad and not was_bad:
        # Open new incident
        incident = Incident(
            reason=reason,
            status="open",
            started_at=datetime.utcnow(),
            **filter_kwargs,
        )
        db.add(incident)
        db.flush()
        await _send_alert(item_type, item_id, item_name, new_status, reason, incident.id, "opened")

    elif not is_bad and was_bad:
        # Close open incident
        q = db.query(Incident).filter(Incident.status == "open")
        if item_type == "device":
            q = q.filter(Incident.device_id == item_id)
        else:
            q = q.filter(Incident.hls_stream_id == item_id)
        open_inc = q.first()

        if open_inc:
            open_inc.status = "resolved"
            open_inc.resolved_at = datetime.utcnow()
            await _send_alert(item_type, item_id, item_name, new_status, "Recovered", open_inc.id, "resolved")


async def _send_alert(
    item_type: str,
    item_id: int,
    item_name: str,
    status: str,
    reason: str,
    incident_id: int,
    event: str,
):
    try:
        from services.alert_service import send_alert
        await send_alert(item_type, item_id, item_name, status, reason, incident_id, event)
    except Exception:
        pass
