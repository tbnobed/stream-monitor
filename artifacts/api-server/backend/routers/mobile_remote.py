"""Public, token-scoped remote-control endpoints for the QR phone remote.

These routes are intentionally NOT behind the session auth dependency: a phone
that scanned the QR code has no login session. Authority comes from the token
itself, which is a 256-bit secret, scoped to a single device, and short-lived
(see services/remote/mobile_tokens.py). Every route resolves the token to a
device id; an unknown or expired token yields 404.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Device
from schemas import RemoteKeyInput, RemoteActionResult, MobileRemoteSession
from services.remote import get_driver, RemoteError, mobile_tokens

router = APIRouter(prefix="/m", tags=["mobile-remote"])
logger = logging.getLogger(__name__)

_CODE_STATUS = {
    "unreachable": 502,
    "not_paired": 409,
    "unsupported": 400,
    "library_missing": 501,
    "error": 400,
}


def _resolve(token: str, db: Session):
    device_id = mobile_tokens.resolve(token)
    if device_id is None:
        raise HTTPException(status_code=404, detail="This remote link has expired. Ask for a fresh QR code.")
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    driver = get_driver(device)
    if driver is None:
        raise HTTPException(status_code=400, detail="This device platform does not support native remote control.")
    return device, driver


def _handle(e: Exception) -> HTTPException:
    if isinstance(e, RemoteError):
        return HTTPException(status_code=_CODE_STATUS.get(e.code, 400), detail=e.message)
    logger.exception("Unexpected mobile-remote error")
    return HTTPException(status_code=502, detail=f"Remote control error: {e}")


@router.get("/{token}", response_model=MobileRemoteSession)
async def mobile_session(token: str, db: Session = Depends(get_db)):
    """One-shot payload the phone page needs: device identity + capabilities + status."""
    device, driver = _resolve(token, db)
    caps = driver.capabilities()
    reachable = False
    paired = False
    detail = None
    try:
        st = await driver.status()
        reachable = st.reachable
        paired = st.paired
        detail = st.detail
    except Exception:
        detail = "Could not verify device connection."
    return MobileRemoteSession(
        device_id=device.id,
        device_name=device.name,
        platform=device.platform,
        protocol=caps.protocol,
        capable=True,
        reachable=reachable,
        paired=paired,
        requires_pairing=caps.requires_pairing,
        keys=caps.keys,
        detail=detail,
    )


@router.post("/{token}/key", response_model=RemoteActionResult)
async def mobile_key(token: str, body: RemoteKeyInput, db: Session = Depends(get_db)):
    device, driver = _resolve(token, db)
    try:
        await driver.send_key(body.key)
    except Exception as e:
        raise _handle(e)
    return RemoteActionResult(ok=True, detail=f"Sent {body.key}")


@router.post("/{token}/revoke", response_model=RemoteActionResult)
async def mobile_revoke(token: str):
    """Invalidate a token. Possessing the token is sufficient authority.

    POST (not DELETE) so the desktop can call it via navigator.sendBeacon on
    window close. Idempotent.
    """
    mobile_tokens.revoke(token)
    return RemoteActionResult(ok=True, detail="revoked")
