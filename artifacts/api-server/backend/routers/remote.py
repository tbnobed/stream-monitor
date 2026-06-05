"""Native remote-control endpoints for a device.

All routes return clear, structured errors (never an unhandled 500). RemoteError
is mapped to an appropriate HTTP status so the UI can surface the reason.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from database import get_db
from models import Device
from schemas import (
    RemoteKeyInput,
    RemoteLaunchInput,
    RemotePairFinishInput,
    RemoteStatusOut,
    RemoteCapabilitiesOut,
    RemoteActionResult,
    RemotePairBeginOut,
    RemoteAppOut,
)
from services.remote import get_driver, RemoteError

router = APIRouter(prefix="/devices/{id}/remote", tags=["remote"])
logger = logging.getLogger(__name__)

_CODE_STATUS = {
    "unreachable": 502,
    "not_paired": 409,
    "unsupported": 400,
    "library_missing": 501,
    "error": 400,
}


def _get_driver_or_404(id: int, db: Session):
    device = db.query(Device).filter(Device.id == id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    driver = get_driver(device)
    if driver is None:
        raise HTTPException(status_code=400, detail="This device platform does not support native remote control.")
    return device, driver


def _handle(e: Exception) -> HTTPException:
    if isinstance(e, RemoteError):
        return HTTPException(status_code=_CODE_STATUS.get(e.code, 400), detail=e.message)
    logger.exception("Unexpected remote-control error")
    return HTTPException(status_code=502, detail=f"Remote control error: {e}")


@router.get("/status", response_model=RemoteStatusOut)
async def remote_status(id: int, db: Session = Depends(get_db)):
    device, driver = _get_driver_or_404(id, db)
    try:
        st = await driver.status()
    except Exception as e:
        raise _handle(e)
    return RemoteStatusOut(
        protocol=st.protocol,
        capable=True,
        reachable=st.reachable,
        paired=st.paired,
        requires_pairing=st.requires_pairing,
        detail=st.detail,
    )


@router.get("/capabilities", response_model=RemoteCapabilitiesOut)
async def remote_capabilities(id: int, db: Session = Depends(get_db)):
    device, driver = _get_driver_or_404(id, db)
    caps = driver.capabilities()
    apps = []
    try:
        apps = await driver.list_apps()
    except Exception:
        apps = []
    return RemoteCapabilitiesOut(
        protocol=caps.protocol,
        capable=True,
        requires_pairing=caps.requires_pairing,
        supports_app_launch=caps.supports_app_launch,
        keys=caps.keys,
        apps=[RemoteAppOut(id=a["id"], name=a["name"]) for a in apps],
    )


@router.post("/key", response_model=RemoteActionResult)
async def remote_key(id: int, body: RemoteKeyInput, db: Session = Depends(get_db)):
    device, driver = _get_driver_or_404(id, db)
    try:
        await driver.send_key(body.key)
    except Exception as e:
        raise _handle(e)
    return RemoteActionResult(ok=True, detail=f"Sent {body.key}")


@router.post("/launch", response_model=RemoteActionResult)
async def remote_launch(id: int, body: RemoteLaunchInput, db: Session = Depends(get_db)):
    device, driver = _get_driver_or_404(id, db)
    try:
        await driver.launch_app(body.app_id)
    except Exception as e:
        raise _handle(e)
    return RemoteActionResult(ok=True, detail=f"Launched {body.app_id}")


@router.post("/pair/begin", response_model=RemotePairBeginOut)
async def remote_pair_begin(id: int, db: Session = Depends(get_db)):
    device, driver = _get_driver_or_404(id, db)
    try:
        result = await driver.pair_begin()
    except Exception as e:
        raise _handle(e)
    if result.config is not None:
        device.remote_config = result.config
        flag_modified(device, "remote_config")
        db.commit()
    return RemotePairBeginOut(ok=True, requires_pin=result.requires_pin, message=result.message)


@router.post("/pair/finish", response_model=RemoteStatusOut)
async def remote_pair_finish(id: int, body: RemotePairFinishInput, db: Session = Depends(get_db)):
    device, driver = _get_driver_or_404(id, db)
    try:
        new_config = await driver.pair_finish(body.pin)
    except Exception as e:
        raise _handle(e)
    device.remote_config = new_config
    flag_modified(device, "remote_config")
    db.commit()
    db.refresh(device)
    # Re-evaluate status with the freshly stored credentials.
    driver = get_driver(device)
    try:
        st = await driver.status()
        return RemoteStatusOut(
            protocol=st.protocol, capable=True, reachable=st.reachable,
            paired=st.paired, requires_pairing=st.requires_pairing, detail=st.detail,
        )
    except Exception:
        return RemoteStatusOut(
            protocol=driver.protocol, capable=True, reachable=False,
            paired=driver.is_paired(), requires_pairing=driver.requires_pairing,
            detail="Paired, but could not verify connection.",
        )
