import logging
import secrets as secrets_mod
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas import AuthConfig, LoginInput, UserOut
from auth import get_current_user, verify_password
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# Cache the OIDC discovery document so we don't refetch it on every login.
_metadata_cache: dict = {}


async def _get_metadata() -> dict:
    if _metadata_cache.get("doc") and _metadata_cache.get("exp", 0) > time.time():
        return _metadata_cache["doc"]
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(settings.oidc_discovery_url)
        resp.raise_for_status()
        doc = resp.json()
    _metadata_cache["doc"] = doc
    _metadata_cache["exp"] = time.time() + 3600
    return doc


def _unique_username(db: Session, base: str | None) -> str:
    base = (base or "user").strip() or "user"
    candidate = base
    i = 1
    while db.query(User).filter(User.username == candidate).first():
        i += 1
        candidate = f"{base}{i}"
    return candidate


def _redirect_uri(request: Request) -> str:
    if settings.oidc_redirect_uri:
        return settings.oidc_redirect_uri
    return str(request.url_for("sso_callback"))


@router.get("/config", response_model=AuthConfig)
def auth_config():
    """Public: tells the frontend whether to show the SSO button."""
    return AuthConfig(sso_enabled=settings.oidc_enabled, sso_label=settings.oidc_display_name)


@router.post("/login", response_model=UserOut)
def login(body: LoginInput, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if (
        not user
        or not user.is_active
        or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    request.session["user_id"] = user.id
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/sso/login")
async def sso_login(request: Request):
    """Begin the Authentik OIDC authorization-code flow."""
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="SSO is not configured")
    meta = await _get_metadata()
    state = secrets_mod.token_urlsafe(32)
    request.session["oidc_state"] = state
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": _redirect_uri(request),
        "scope": "openid email profile",
        "state": state,
    }
    return RedirectResponse(url=f"{meta['authorization_endpoint']}?{urlencode(params)}")


@router.get("/sso/callback", name="sso_callback")
async def sso_callback(request: Request, db: Session = Depends(get_db)):
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="SSO is not configured")

    if request.query_params.get("error"):
        logger.warning("OIDC provider returned error: %s", request.query_params.get("error"))
        return RedirectResponse(url="/?sso_error=1")

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    saved_state = request.session.pop("oidc_state", None)
    if not code or not state or state != saved_state:
        logger.warning("OIDC callback state mismatch or missing code")
        return RedirectResponse(url="/?sso_error=1")

    meta = await _get_metadata()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                meta["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _redirect_uri(request),
                    "client_id": settings.oidc_client_id,
                    "client_secret": settings.oidc_client_secret,
                },
                headers={"Accept": "application/json"},
            )
            if token_resp.status_code != 200:
                logger.warning("OIDC token exchange failed: %s %s", token_resp.status_code, token_resp.text[:300])
                return RedirectResponse(url="/?sso_error=1")
            access_token = token_resp.json().get("access_token")
            if not access_token:
                return RedirectResponse(url="/?sso_error=1")
            userinfo_resp = await client.get(
                meta["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo_resp.raise_for_status()
            userinfo = userinfo_resp.json()
    except httpx.HTTPError as exc:
        logger.warning("OIDC callback HTTP error: %s", exc)
        return RedirectResponse(url="/?sso_error=1")

    sub = userinfo.get("sub")
    if not sub:
        return RedirectResponse(url="/?sso_error=1")
    email = userinfo.get("email")
    # Only trust the email claim when the provider asserts it is verified;
    # an unverified address must never feed identity or account decisions.
    email_verified = bool(userinfo.get("email_verified"))
    trusted_email = email if (email and email_verified) else None
    full_name = userinfo.get("name")
    preferred = userinfo.get("preferred_username") or trusted_email or sub

    # Authenticate strictly by the stable OIDC subject. We deliberately do NOT
    # link to an existing account by email: doing so would let an SSO identity
    # take over a local account (including admin) simply by presenting a
    # matching address. A given `sub` maps to exactly one account.
    user = db.query(User).filter(User.oidc_subject == sub).first()

    if not user:
        # Auto-provision first-time SSO users as operators.
        user = User(
            username=_unique_username(db, preferred),
            email=trusted_email,
            full_name=full_name,
            role="operator",
            auth_provider="oidc",
            oidc_subject=sub,
            is_active=True,
        )
        db.add(user)
    else:
        # Backfill missing profile fields only; never reassign the subject or
        # change an established role/email from the token.
        if trusted_email and not user.email:
            user.email = trusted_email
        if full_name and not user.full_name:
            user.full_name = full_name

    if not user.is_active:
        return RedirectResponse(url="/?sso_error=disabled")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    request.session["user_id"] = user.id
    return RedirectResponse(url="/")
