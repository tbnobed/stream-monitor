from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import HlsStream, CheckResult
from schemas import HlsStreamInput, HlsStreamUpdate, HlsStreamOut, ItemStats, CheckResultOut
from routers.devices import _calc_stats

router = APIRouter(prefix="/hls-streams", tags=["hls-streams"])


@router.get("/", response_model=list[HlsStreamOut])
def list_hls_streams(db: Session = Depends(get_db)):
    return db.query(HlsStream).order_by(HlsStream.id).all()


@router.post("/", response_model=HlsStreamOut, status_code=201)
def create_hls_stream(body: HlsStreamInput, db: Session = Depends(get_db)):
    stream = HlsStream(**body.model_dump())
    db.add(stream)
    db.commit()
    db.refresh(stream)
    return stream


@router.get("/{id}", response_model=HlsStreamOut)
def get_hls_stream(id: int, db: Session = Depends(get_db)):
    stream = db.query(HlsStream).filter(HlsStream.id == id).first()
    if not stream:
        raise HTTPException(status_code=404, detail="HLS stream not found")
    return stream


@router.patch("/{id}", response_model=HlsStreamOut)
def update_hls_stream(id: int, body: HlsStreamUpdate, db: Session = Depends(get_db)):
    stream = db.query(HlsStream).filter(HlsStream.id == id).first()
    if not stream:
        raise HTTPException(status_code=404, detail="HLS stream not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(stream, k, v)
    db.commit()
    db.refresh(stream)
    return stream


@router.delete("/{id}", status_code=204)
def delete_hls_stream(id: int, db: Session = Depends(get_db)):
    stream = db.query(HlsStream).filter(HlsStream.id == id).first()
    if not stream:
        raise HTTPException(status_code=404, detail="HLS stream not found")
    db.delete(stream)
    db.commit()


@router.get("/{id}/stats/{window}", response_model=ItemStats)
def get_hls_stream_stats(id: int, window: str, db: Session = Depends(get_db)):
    stream = db.query(HlsStream).filter(HlsStream.id == id).first()
    if not stream:
        raise HTTPException(status_code=404, detail="HLS stream not found")
    return _calc_stats(db, window, hls_stream_id=id)


@router.get("/{id}/latest-check", response_model=CheckResultOut)
def get_hls_stream_latest_check(id: int, db: Session = Depends(get_db)):
    result = (
        db.query(CheckResult)
        .filter(CheckResult.hls_stream_id == id)
        .order_by(CheckResult.timestamp.desc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="No check results found")
    return result
