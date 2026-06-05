from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import GuacamoleSession
from schemas import GuacamoleSessionInput, GuacamoleSessionUpdate, GuacamoleSessionOut

router = APIRouter(prefix="/guacamole-sessions", tags=["guacamole"])


@router.get("", response_model=list[GuacamoleSessionOut])
def list_sessions(db: Session = Depends(get_db)):
    return db.query(GuacamoleSession).order_by(GuacamoleSession.id).all()


@router.post("", response_model=GuacamoleSessionOut, status_code=201)
def create_session(data: GuacamoleSessionInput, db: Session = Depends(get_db)):
    session = GuacamoleSession(**data.model_dump())
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.patch("/{id}", response_model=GuacamoleSessionOut)
def update_session(id: int, data: GuacamoleSessionUpdate, db: Session = Depends(get_db)):
    session = db.query(GuacamoleSession).filter(GuacamoleSession.id == id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(session, field, value)
    db.commit()
    db.refresh(session)
    return session


@router.delete("/{id}", status_code=204)
def delete_session(id: int, db: Session = Depends(get_db)):
    session = db.query(GuacamoleSession).filter(GuacamoleSession.id == id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(session)
    db.commit()
