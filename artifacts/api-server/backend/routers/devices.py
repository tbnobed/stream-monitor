from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import Device, Incident, CheckResult
from schemas import DeviceInput, DeviceUpdate, DeviceOut, ItemStats, CheckResultOut
from services.remote import remote_info
from datetime import datetime, timedelta

router = APIRouter(prefix="/devices", tags=["devices"])


def _serialize(device: Device) -> DeviceOut:
    out = DeviceOut.model_validate(device)
    info = remote_info(device)
    out.remote_protocol = info["protocol"]
    out.remote_capable = info["capable"]
    out.remote_requires_pairing = info["requires_pairing"]
    out.remote_paired = info["paired"]
    return out


@router.get("/", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db)):
    return [_serialize(d) for d in db.query(Device).order_by(Device.id).all()]


@router.post("/", response_model=DeviceOut, status_code=201)
def create_device(body: DeviceInput, db: Session = Depends(get_db)):
    device = Device(**body.model_dump())
    db.add(device)
    db.commit()
    db.refresh(device)
    return _serialize(device)


@router.get("/{id}", response_model=DeviceOut)
def get_device(id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return _serialize(device)


@router.patch("/{id}", response_model=DeviceOut)
def update_device(id: int, body: DeviceUpdate, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(device, k, v)
    db.commit()
    db.refresh(device)
    return _serialize(device)


@router.delete("/{id}", status_code=204)
def delete_device(id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    db.delete(device)
    db.commit()


@router.get("/{id}/stats/{window}", response_model=ItemStats)
def get_device_stats(id: int, window: str, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return _calc_stats(db, window, device_id=id)


@router.get("/{id}/latest-check", response_model=CheckResultOut)
def get_device_latest_check(id: int, db: Session = Depends(get_db)):
    result = (
        db.query(CheckResult)
        .filter(CheckResult.device_id == id)
        .order_by(CheckResult.timestamp.desc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="No check results found")
    return result


def _calc_stats(db: Session, window: str, device_id: int = None, hls_stream_id: int = None) -> ItemStats:
    windows = {"24h": 24, "7d": 168, "30d": 720}
    hours = windows.get(window, 24)
    since = datetime.utcnow() - timedelta(hours=hours)

    q = db.query(Incident)
    if device_id:
        q = q.filter(Incident.device_id == device_id)
    else:
        q = q.filter(Incident.hls_stream_id == hls_stream_id)
    q = q.filter(Incident.started_at >= since)
    incidents = q.all()

    total_down_seconds = 0
    mttr_values = []
    for inc in incidents:
        end = inc.resolved_at or datetime.utcnow()
        duration = (end - inc.started_at).total_seconds()
        total_down_seconds += duration
        if inc.resolved_at:
            mttr_values.append(duration)

    total_seconds = hours * 3600
    uptime_pct = max(0.0, (1 - total_down_seconds / total_seconds) * 100) if total_seconds > 0 else 100.0
    mttr = sum(mttr_values) / len(mttr_values) if mttr_values else None

    return ItemStats(
        uptime_pct=round(uptime_pct, 2),
        total_incidents=len(incidents),
        mttr_seconds=round(mttr, 1) if mttr else None,
        window=window,
    )
