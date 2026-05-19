import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt

from app.config import Settings, get_settings
from app.rbac import user_role

router = APIRouter(prefix="/auth")

_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"
_GITHUB_TEAMS_URL = "https://api.github.com/user/teams"
COOKIE_NAME = "bff_session"
CSRF_COOKIE = "csrf_token"


def _create_jwt(payload: dict, settings: Settings) -> str:
    exp = datetime.now(timezone.utc) + timedelta(seconds=settings.jwt_ttl_seconds)
    return jwt.encode({**payload, "exp": exp}, settings.jwt_secret, algorithm="HS256")


def _decode_jwt(token: str, settings: Settings) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        return None


def _cookie_options(settings: Settings) -> dict:
    options: dict = {
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite.lower(),
        "path": "/",
    }
    if settings.cookie_domain:
        options["domain"] = settings.cookie_domain
    return options


def _set_session_cookies(response: Response, session_token: str, csrf: str, settings: Settings) -> None:
    options = _cookie_options(settings)
    response.set_cookie(
        COOKIE_NAME,
        session_token,
        httponly=True,
        max_age=settings.jwt_ttl_seconds,
        **options,
    )
    # Non-httponly so the frontend can read and send as X-CSRF-Token header.
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        httponly=False,
        max_age=settings.jwt_ttl_seconds,
        **options,
    )


def _delete_session_cookies(response: Response, settings: Settings) -> None:
    options = _cookie_options(settings)
    response.delete_cookie(COOKIE_NAME, **options)
    response.delete_cookie(CSRF_COOKIE, **options)


def get_current_user(request: Request, settings: Settings = Depends(get_settings)) -> Optional[dict]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return _decode_jwt(token, settings)


async def _fetch_github_teams(access_token: str) -> list[str]:
    """Return list of 'org/team-slug' strings for the authenticated user."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                _GITHUB_TEAMS_URL,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            if r.status_code != 200:
                return []
            items = r.json()
            return [
                f"{t['organization']['login']}/{t['slug']}"
                for t in items
                if isinstance(t, dict) and "slug" in t and "organization" in t
            ]
    except Exception:
        return []


@router.get("/login")
async def login(settings: Settings = Depends(get_settings)):
    if not settings.github_client_id:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured — set GITHUB_CLIENT_ID")
    url = (
        f"{_GITHUB_AUTH_URL}"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_callback_url}"
        f"&scope=read:user%20read:org"
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

    teams = await _fetch_github_teams(access_token)
    login_name = user_data.get("login", "unknown")
    csrf = secrets.token_urlsafe(32)

    session_token = _create_jwt(
        {
            "sub": login_name,
            "name": user_data.get("name") or login_name,
            "teams": teams,
            "csrf": csrf,
        },
        settings,
    )
    resp = RedirectResponse(url=settings.frontend_url, status_code=302)
    _set_session_cookies(resp, session_token, csrf, settings)
    return resp


@router.get("/me")
async def me(request: Request, settings: Settings = Depends(get_settings)):
    payload = get_current_user(request, settings)
    if not payload:
        raise HTTPException(status_code=401, detail="Not authenticated")
    role = user_role(payload["sub"], settings, payload.get("teams", []))
    return {"user": payload["sub"], "name": payload.get("name", payload["sub"]), "role": role}


@router.post("/logout")
async def logout(response: Response, settings: Settings = Depends(get_settings)):
    _delete_session_cookies(response, settings)
    return {"ok": True}
