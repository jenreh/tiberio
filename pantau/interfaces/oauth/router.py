"""OAuth2 Authorization Server — Authorization Code Grant + PKCE.

Endpoints:
  GET  /oauth/authorize  — show login form
  POST /oauth/authorize  — authenticate user, issue auth code, redirect
  POST /oauth/token      — exchange code → tokens, or refresh → new tokens
"""

from __future__ import annotations

import asyncio
import hashlib
import html as _html
import logging
import secrets
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import bcrypt as _bcrypt
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from pantau.adapters.auth_code_store import AuthCodeStore
from pantau.adapters.jwt_service import JwtService
from pantau.ports.user_store_port import UserStorePort

log = logging.getLogger(__name__)

oauth_router = APIRouter(prefix="/oauth", tags=["oauth"])


def _verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    """Hash a plain-text password for storage."""
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


_LOGIN_FORM_HTML = """\
<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title>pantau-alexa Login</title></head>
<body>
<h1>Anmelden</h1>
<form method="post">
  <input type="hidden" name="redirect_uri" value="{redirect_uri}">
  <input type="hidden" name="client_id" value="{client_id}">
  <input type="hidden" name="code_challenge" value="{code_challenge}">
  <input type="hidden" name="code_challenge_method" value="{code_challenge_method}">
  <input type="hidden" name="state" value="{state}">
  <label>Benutzername: <input type="text" name="username" required></label><br>
  <label>Passwort: <input type="password" name="password" required></label><br>
  <button type="submit">Anmelden</button>
</form>
{error}
</body>
</html>
"""


def _render_login(
    redirect_uri: str,
    client_id: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str,
    error: str = "",
) -> str:
    # All user-controlled values are HTML-escaped before interpolation (XSS prevention)
    error_html = f"<p style='color:red'>{_html.escape(error)}</p>" if error else ""
    return _LOGIN_FORM_HTML.format(
        redirect_uri=_html.escape(redirect_uri, quote=True),
        client_id=_html.escape(client_id, quote=True),
        code_challenge=_html.escape(code_challenge, quote=True),
        code_challenge_method=_html.escape(code_challenge_method, quote=True),
        state=_html.escape(state, quote=True),
        error=error_html,
    )


def _check_redirect_uri(redirect_uri: str, allowed: list[str]) -> bool:
    """Return True if redirect_uri is permitted.

    When the allowlist is empty the server is in dev mode; any URI is accepted
    but a warning is logged. In production, set OAUTH_ALLOWED_REDIRECT_URIS.
    """
    if not allowed:
        log.warning(
            "oauth_allowed_redirect_uris is empty — accepting any redirect_uri "
            "(set OAUTH_ALLOWED_REDIRECT_URIS in production)"
        )
        return True
    return redirect_uri in allowed


def _verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    if method == "S256":
        digest = hashlib.sha256(code_verifier.encode()).digest()
        computed = urlsafe_b64encode(digest).rstrip(b"=").decode()
        return secrets.compare_digest(computed, code_challenge)
    if method == "plain":
        return secrets.compare_digest(code_verifier, code_challenge)
    return False


def _oauth_error(error: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": error, "error_description": description},
        status_code=status,
    )


# ---------------------------------------------------------------------------
# GET /oauth/authorize — show login form
# ---------------------------------------------------------------------------


@oauth_router.get("/authorize")
async def authorize_get(
    request: Request,
    redirect_uri: str,
    client_id: str,
    code_challenge: str,
    response_type: str = "code",
    code_challenge_method: str = "S256",
    state: str = "",
) -> HTMLResponse:
    allowed: list[str] = getattr(
        request.app.state.settings, "oauth_allowed_redirect_uris", []
    )
    if not _check_redirect_uri(redirect_uri, allowed):
        return HTMLResponse(
            "<h1>400 Bad Request — redirect_uri not permitted</h1>", status_code=400
        )

    if response_type != "code":
        return HTMLResponse(
            "<h1>400 Bad Request — unsupported_response_type</h1>", status_code=400
        )

    html = _render_login(
        redirect_uri=redirect_uri,
        client_id=client_id,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        state=state,
    )
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# POST /oauth/authorize — validate credentials, issue auth code
# ---------------------------------------------------------------------------


@oauth_router.post("/authorize", response_model=None)
async def authorize_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    redirect_uri: str = Form(...),
    client_id: str = Form(...),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form("S256"),
    state: str = Form(""),
) -> HTMLResponse | RedirectResponse:
    allowed: list[str] = getattr(
        request.app.state.settings, "oauth_allowed_redirect_uris", []
    )
    if not _check_redirect_uri(redirect_uri, allowed):
        return HTMLResponse(
            "<h1>400 Bad Request — redirect_uri not permitted</h1>", status_code=400
        )

    user_store = request.app.state.container.get(UserStorePort)  # type: ignore[type-abstract]
    auth_codes: AuthCodeStore = request.app.state.container.get(AuthCodeStore)

    user = await user_store.get_user_by_username(username)

    # bcrypt is CPU-bound — run in executor to avoid blocking the event loop
    loop = asyncio.get_running_loop()
    password_ok = user is not None and await loop.run_in_executor(
        None, _verify_password, password, user.password_hash
    )

    if not password_ok:
        log.warning("Login failed for username: %s", username)
        html = _render_login(
            redirect_uri=redirect_uri,
            client_id=client_id,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            state=state,
            error="Ungültiger Benutzername oder Passwort.",
        )
        return HTMLResponse(html, status_code=401)

    code = await auth_codes.save(
        user_id=user.id,  # type: ignore[union-attr]
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
    )

    params: dict[str, str] = {"code": code}
    if state:
        params["state"] = state

    redirect_url = f"{redirect_uri}?{urlencode(params)}"
    log.info("Auth code issued for user %s → %s", username, client_id)
    return RedirectResponse(redirect_url, status_code=302)


# ---------------------------------------------------------------------------
# POST /oauth/token — exchange code or refresh token
# ---------------------------------------------------------------------------


@oauth_router.post("/token")
async def token_post(
    request: Request,
    grant_type: str = Form(...),
    code: str | None = Form(None),
    code_verifier: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    client_id: str | None = Form(None),
    refresh_token: str | None = Form(None),
) -> JSONResponse:
    jwt_service: JwtService = request.app.state.container.get(JwtService)
    user_store = request.app.state.container.get(UserStorePort)  # type: ignore[type-abstract]
    auth_codes: AuthCodeStore = request.app.state.container.get(AuthCodeStore)
    settings = request.app.state.settings

    if grant_type == "authorization_code":
        return await _handle_code_exchange(
            code=code,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
            client_id=client_id,
            auth_codes=auth_codes,
            jwt_service=jwt_service,
            user_store=user_store,
            settings=settings,
        )

    if grant_type == "refresh_token":
        return await _handle_refresh(
            refresh_token=refresh_token,
            jwt_service=jwt_service,
            user_store=user_store,
            settings=settings,
        )

    return _oauth_error(
        "unsupported_grant_type", f"Unsupported grant_type: {grant_type!r}"
    )


async def _handle_code_exchange(
    *,
    code: str | None,
    code_verifier: str | None,
    redirect_uri: str | None,
    client_id: str | None,
    auth_codes: AuthCodeStore,
    jwt_service: JwtService,
    user_store: UserStorePort,
    settings: object,
) -> JSONResponse:
    if not code or not code_verifier or not redirect_uri:
        return _oauth_error(
            "invalid_request", "code, code_verifier and redirect_uri are required"
        )

    # Validate all claims against the stored entry BEFORE consuming it.
    # This prevents a mismatched redirect_uri or client_id from permanently
    # consuming the code and locking out the legitimate client.
    entry = await auth_codes.lookup(code)
    if entry is None:
        return _oauth_error("invalid_grant", "Authorization code invalid or expired")

    if entry.redirect_uri != redirect_uri:
        return _oauth_error("invalid_grant", "redirect_uri mismatch")

    if client_id is not None and entry.client_id != client_id:
        return _oauth_error("invalid_grant", "client_id mismatch")

    if not _verify_pkce(
        code_verifier, entry.code_challenge, entry.code_challenge_method
    ):
        return _oauth_error("invalid_grant", "PKCE verification failed")

    # Atomically consume — guards against concurrent token requests with the same code
    consumed = await auth_codes.redeem(code)
    if consumed is None:
        return _oauth_error("invalid_grant", "Authorization code already used")

    return await _issue_token_pair(
        user_id=entry.user_id,
        jwt_service=jwt_service,
        user_store=user_store,
        settings=settings,
    )


async def _handle_refresh(
    *,
    refresh_token: str | None,
    jwt_service: JwtService,
    user_store: UserStorePort,
    settings: object,
) -> JSONResponse:
    if not refresh_token:
        return _oauth_error("invalid_request", "refresh_token is required")

    # Atomic check-and-revoke — prevents concurrent requests from both succeeding
    user_id = await user_store.pop_refresh_token(refresh_token)
    if user_id is None:
        return _oauth_error("invalid_grant", "Refresh token invalid or expired")

    return await _issue_token_pair(
        user_id=user_id,
        jwt_service=jwt_service,
        user_store=user_store,
        settings=settings,
    )


async def _issue_token_pair(
    *,
    user_id: str,
    jwt_service: JwtService,
    user_store: UserStorePort,
    settings: object,
) -> JSONResponse:
    access_token, expires_in = jwt_service.issue_access_token(user_id)
    new_refresh_token = jwt_service.issue_refresh_token()

    refresh_expire_days: int = getattr(settings, "jwt_refresh_token_expire_days", 30)
    expires_at = datetime.now(UTC) + timedelta(days=refresh_expire_days)
    await user_store.save_refresh_token(new_refresh_token, user_id, expires_at)

    log.info("Token pair issued for user %s", user_id)
    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "refresh_token": new_refresh_token,
        }
    )
