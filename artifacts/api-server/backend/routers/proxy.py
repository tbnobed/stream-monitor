from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Setting
import httpx
import logging

router = APIRouter(prefix="/proxy", tags=["proxy"])
logger = logging.getLogger(__name__)


def get_setting_value(key: str, default: str) -> str:
    try:
        db = SessionLocal()
        s = db.query(Setting).filter(Setting.key == key).first()
        db.close()
        return s.value if s else default
    except Exception:
        return default


@router.post("/whep")
@router.post("/whep/")
async def whep_proxy(request: Request, stream: str):
    """Proxy WHEP SDP offer to SRS server and return SDP answer."""
    whep_base = get_setting_value("srs_whep_base_url", "http://cdn1.obedtv.live:2023")
    target_url = f"{whep_base}/rtc/v1/whep/?app=live&stream={stream}"

    body = await request.body()
    headers = {
        "Content-Type": request.headers.get("Content-Type", "application/sdp"),
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(target_url, content=body, headers=headers)
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("Content-Type", "application/sdp"),
            headers={k: v for k, v in resp.headers.items() if k.lower() not in ("content-length", "transfer-encoding", "location")},
        )
    except Exception as e:
        logger.error(f"WHEP proxy error: {e}")
        raise HTTPException(status_code=502, detail=f"WHEP upstream error: {e}")


@router.get("/srs/{path:path}")
async def srs_api_proxy(path: str, request: Request):
    """Proxy SRS HTTP API calls."""
    srs_base = get_setting_value("srs_api_base_url", "http://cdn1.obedtv.live:1985/api/v1")
    target_url = f"{srs_base}/{path}"
    params = dict(request.query_params)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(target_url, params=params)
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("Content-Type", "application/json"),
        )
    except Exception as e:
        logger.error(f"SRS API proxy error: {e}")
        raise HTTPException(status_code=502, detail=f"SRS API upstream error: {e}")


@router.api_route("/guacamole/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def guacamole_proxy(path: str, request: Request):
    """Proxy all Guacamole requests to avoid mixed-content blocking."""
    guac_base = get_setting_value("guacamole_base_url", "http://cdn3.obedtv.live:8088/guacamole")
    target_url = f"{guac_base}/{path}"
    params = dict(request.query_params)

    body = await request.body()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }
    headers["Host"] = guac_base.split("//", 1)[-1].split("/")[0]

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                params=params,
                content=body,
                headers=headers,
            )

        response_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in ("content-length", "transfer-encoding", "connection")
        }

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=response_headers,
            media_type=resp.headers.get("Content-Type"),
        )
    except Exception as e:
        logger.error(f"Guacamole proxy error: {e}")
        raise HTTPException(status_code=502, detail=f"Guacamole upstream error: {e}")
