from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from database import get_db
from models import Device, HlsStream, Incident
from schemas import DashboardSummary, IncidentOut
from routers.incidents import _enrich

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)):
    devices = db.query(Device).all()
    hls_streams = db.query(HlsStream).all()
    open_incidents = db.query(Incident).filter(Incident.status == "open").count()

    def count_status(items, status):
        return sum(1 for i in items if i.current_status == status)

    return DashboardSummary(
        total_devices=len(devices),
        total_hls_streams=len(hls_streams),
        devices_down=count_status(devices, "DOWN"),
        devices_warning=count_status(devices, "WARNING"),
        devices_healthy=count_status(devices, "HEALTHY"),
        devices_unknown=count_status(devices, "UNKNOWN"),
        hls_down=count_status(hls_streams, "DOWN"),
        hls_warning=count_status(hls_streams, "WARNING"),
        hls_healthy=count_status(hls_streams, "HEALTHY"),
        hls_unknown=count_status(hls_streams, "UNKNOWN"),
        open_incidents=open_incidents,
    )


@router.get("/recent-incidents", response_model=list[IncidentOut])
def get_recent_incidents(
    limit: int = Query(10, le=100),
    db: Session = Depends(get_db),
):
    incidents = (
        db.query(Incident)
        .order_by(Incident.started_at.desc())
        .limit(limit)
        .all()
    )
    return [_enrich(i) for i in incidents]
