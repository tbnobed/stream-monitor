from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import Device, Incident, CheckResult, Setting
from schemas import (
    DeviceInput, DeviceUpdate, DeviceOut, ItemStats, CheckResultOut,
    LogoReferenceRequest, LogoReferenceResult,
)
from services.remote import remote_info
from services import logo as logo_svc
from datetime import datetime, timedelta

router = APIRouter(prefix="/devices", tags=["devices"])


def _serialize(device: Device) -> DeviceOut:
    out = DeviceOut.model_validate(device)
    info = remote_info(device)
    out.remote_protocol = info["protocol"]
    out.remote_capable = info["capable"]
    out.remote_requires_pairing = info["requires_pairing"]
    out.remote_paired = info["paired"]
    out.logo_reference_set = bool(device.logo_template)
    return out


@router.get("", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db)):
    return [_serialize(d) for d in db.query(Device).order_by(Device.id).all()]


@router.post("", response_model=DeviceOut, status_code=201)
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
    NON_NULLABLE = {"logo_check_enabled", "logo_match_threshold"}
    for k, v in body.model_dump(exclude_unset=True).items():
        if k in NON_NULLABLE and v is None:
            continue
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


@router.post("/{id}/logo/reference", response_model=LogoReferenceResult)
async def capture_logo_reference(
    id: int, body: LogoReferenceRequest, db: Session = Depends(get_db)
):
    """Grab a live frame from the device's stream for logo-reference setup.

    Always returns a full snapshot plus the cropped region so the operator can
    align the box. When ``save`` is true, the cropped region is stored as the
    device's logo template (and logo monitoring is enabled).
    """
    device = db.query(Device).filter(Device.id == id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    s = db.query(Setting).filter(Setting.key == "srs_whep_base_url").first()
    whep_base = s.value if s else "http://cdn1.obedtv.live:2023"

    frame = await logo_svc.grab_video_frame(
        whep_base, device.srs_app, device.srs_stream_key
    )
    if frame is None:
        return LogoReferenceResult(
            captured=False,
            message="No video frames received from the stream — is it live?",
        )

    h, w = frame.shape[:2]
    region = {"x": body.region.x, "y": body.region.y, "w": body.region.w, "h": body.region.h}

    snapshot_url = logo_svc.encode_jpeg_data_url(frame)
    gray_crop = logo_svc.crop_region(logo_svc.rgb_to_gray(frame), region)
    rgb_crop = logo_svc.crop_region(frame, region)
    crop_url = logo_svc.encode_png_data_url(rgb_crop) if rgb_crop.size else None

    # Score this region against the already-saved reference (if any) BEFORE we
    # overwrite it, so the operator gets live feedback on how strongly the
    # current box matches — the missing signal that made tuning feel "flimsy".
    match_score = None
    existing_tmpl = (
        logo_svc.decode_template(device.logo_template) if device.logo_template else None
    )
    if existing_tmpl is not None and gray_crop.size:
        match_score = round(
            logo_svc.match_score(existing_tmpl, logo_svc.rgb_to_gray(frame), region), 3
        )

    saved = False
    if body.save and gray_crop.size:
        device.logo_template = logo_svc.build_template_b64(gray_crop)
        device.logo_region = region
        device.logo_check_enabled = True
        if body.threshold is not None:
            device.logo_match_threshold = body.threshold
        db.commit()
        db.refresh(device)
        saved = True

    return LogoReferenceResult(
        captured=True,
        snapshot=snapshot_url,
        crop=crop_url,
        width=w,
        height=h,
        saved=saved,
        match_score=match_score,
    )


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
