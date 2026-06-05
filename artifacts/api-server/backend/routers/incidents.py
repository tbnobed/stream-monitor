from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
from models import Incident, Device, HlsStream
from schemas import IncidentOut, AcknowledgeInput

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _enrich(incident: Incident) -> dict:
    d = {
        "id": incident.id,
        "device_id": incident.device_id,
        "hls_stream_id": incident.hls_stream_id,
        "device_name": incident.device.name if incident.device else None,
        "hls_stream_name": incident.hls_stream.name if incident.hls_stream else None,
        "item_type": "device" if incident.device_id else "hls_stream",
        "started_at": incident.started_at,
        "resolved_at": incident.resolved_at,
        "status": incident.status,
        "reason": incident.reason,
        "acknowledged_by": incident.acknowledged_by,
    }
    return d


@router.get("/", response_model=list[IncidentOut])
def list_incidents(
    device_id: Optional[int] = Query(None),
    hls_stream_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
):
    q = db.query(Incident)
    if device_id is not None:
        q = q.filter(Incident.device_id == device_id)
    if hls_stream_id is not None:
        q = q.filter(Incident.hls_stream_id == hls_stream_id)
    if status:
        q = q.filter(Incident.status == status)
    incidents = q.order_by(Incident.started_at.desc()).limit(limit).all()
    return [_enrich(i) for i in incidents]


@router.get("/{id}", response_model=IncidentOut)
def get_incident(id: int, db: Session = Depends(get_db)):
    incident = db.query(Incident).filter(Incident.id == id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _enrich(incident)


@router.patch("/{id}/acknowledge", response_model=IncidentOut)
def acknowledge_incident(id: int, body: AcknowledgeInput, db: Session = Depends(get_db)):
    incident = db.query(Incident).filter(Incident.id == id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident.acknowledged_by = body.acknowledged_by
    db.commit()
    db.refresh(incident)
    return _enrich(incident)
