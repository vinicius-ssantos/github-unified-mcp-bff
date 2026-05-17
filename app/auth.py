from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from jose import jwt, JWTError

from app.config import Settings, get_settings

router = APIRouter(prefix="/auth")

_GITHUB_AUTH_URL  = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL  = "https://api.github.com/user"
COOKIE_NAME = "bff_session"


def _create_jwt(payload: dict, settings: Settings) -> str:
    exp = datetime.now(timezone.utc) + timedelta(seconds=settings.jwt_ttl_seconds)
    return jwt.encode({**payload, "exp": exp}, settings.jwt_secret, algorithm="HS256")


def _decode_jwt(token: str, settings: Settings) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        return None


def get_current_user(request: Request, settings: Settings = Depends(get_settings)) -> Optional[dict]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return _decode_jwt(token, settings)


@router.get("/login")
async def login(settings: Settings = Depends(get_settings)):
    if not settings.github_client_id:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured — set GITHUB_CLIENT_ID")
    url = (
        f"{_GITHUB_AUTH_URL}"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_callback_url}"
        f"&scope=read:user"
    )
    return RedirectResponse(url)


@router.get("/callback")
async def callback(code: str, settings: Settings = Depends(get_settings)):
    if not settings.github_client_id:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            _GITHUB_TOKEN_URL,
            json={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        access_token = r.json().get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="GitHub token exchange failed")

        r = await client.get(
            _GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        user_data = r.json()

    login_name = user_data.get("login", "unknown")
    session_token = _create_jwt(
        {"sub": login_name, "name": user_data.get("name") or login_name},
        settings,
    )
    resp = RedirectResponse(url="/auth/me", status_code=302)
    resp.set_cookie(
        COOKIE_NAME,
        session_token,
        httponly=True,
        samesite="lax",
        max_age=settings.jwt_ttl_seconds,
    )
    return resp


@router.get("/me")
async def me(request: Request, settings: Settings = Depends(get_settings)):
    payload = get_current_user(request, settings)
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user": payload["sub"], "name": payload.get("name", payload["sub"])}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, samesite="lax")
    return {"ok": True}
