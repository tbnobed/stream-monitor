from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
from models import CheckResult
from schemas import CheckResultOut

router = APIRouter(prefix="/check-results", tags=["check-results"])


@router.get("/", response_model=list[CheckResultOut])
def list_check_results(
    device_id: Optional[int] = Query(None),
    hls_stream_id: Optional[int] = Query(None),
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(CheckResult)
    if device_id is not None:
        q = q.filter(CheckResult.device_id == device_id)
    if hls_stream_id is not None:
        q = q.filter(CheckResult.hls_stream_id == hls_stream_id)
    return q.order_by(CheckResult.timestamp.desc()).limit(limit).all()
