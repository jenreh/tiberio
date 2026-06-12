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

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from pantau.config.settings import Settings
from pantau.ports.auth_code_store_port import AuthCodeStorePort
from pantau.ports.password_hasher_port import PasswordHasherPort
from pantau.ports.token_issuer_port import TokenIssuerPort
from pantau.ports.user_store_port import UserStorePort

log = logging.getLogger(__name__)

oauth_router = APIRouter(prefix="/oauth", tags=["oauth"])


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


def _check_redirect_uri(
    redirect_uri: str, allowed: list[str], *, dev_mode: bool
) -> bool:
    """Return True if redirect_uri is permitted.

    When the allowlist is empty:
    - dev_mode=True  → accept any URI (log a warning)
    - dev_mode=False → reject (fail-closed; prevents accidental production exposure)
    """
    if not allowed:
        if dev_mode:
            log.warning(
                "DEV_MODE is on and oauth_allowed_redirect_uris is empty — "
                "accepting any redirect_uri. Do NOT use in production."
            )
            return True
        return False
    return redirect_uri in allowed


def _verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    # Only S256 is accepted; 'plain' would downgrade PKCE to a bearer secret.
    if method == "S256":
        digest = hashlib.sha256(code_verifier.encode()).digest()
        computed = urlsafe_b64encode(digest).rstrip(b"=").decode()
        return secrets.compare_digest(computed, code_challenge)
    return False


def _oauth_error(error: str, description: str, status: int = 400) -> JSONResponse:
    # description never contains secrets, codes or tokens — safe to log.
    log.warning("OAuth error response (%d %s): %s", status, error, description)
    return JSONResponse(
        {"error": error, "error_description": description},
        status_code=status,
    )


# ---------------------------------------------------------------------------
# GET /oauth/authorize — show login form
# ---------------------------------------------------------------------------


def _redirect_uri_error(allowed: list[str], dev_mode: bool) -> HTMLResponse:
    """Return the appropriate error response for a redirect_uri check failure."""
    if not allowed and not dev_mode:
        return HTMLResponse(
            "<h1>503 Service Unavailable — OAuth not configured</h1>"
            "<p>Set PANTAU_OAUTH_ALLOWED_REDIRECT_URIS or enable PANTAU_DEV_MODE for local dev.</p>",
            status_code=503,
        )
    return HTMLResponse(
        "<h1>400 Bad Request — redirect_uri not permitted</h1>", status_code=400
    )


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
    settings: Settings = request.app.state.settings
    allowed = settings.oauth_allowed_redirect_uris
    dev_mode = settings.dev_mode
    if not _check_redirect_uri(redirect_uri, allowed, dev_mode=dev_mode):
        return _redirect_uri_error(allowed, dev_mode)

    if response_type != "code":
        return HTMLResponse(
            "<h1>400 Bad Request — unsupported_response_type</h1>", status_code=400
        )

    if code_challenge_method != "S256":
        return HTMLResponse(
            "<h1>400 Bad Request — only code_challenge_method=S256 is supported</h1>",
            status_code=400,
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
    settings: Settings = request.app.state.settings
    allowed = settings.oauth_allowed_redirect_uris
    dev_mode = settings.dev_mode
    if not _check_redirect_uri(redirect_uri, allowed, dev_mode=dev_mode):
        return _redirect_uri_error(allowed, dev_mode)

    if code_challenge_method != "S256":
        return HTMLResponse(
            "<h1>400 Bad Request — only code_challenge_method=S256 is supported</h1>",
            status_code=400,
        )

    client_ip = request.client.host if request.client else "unknown"
    ip_allowed = request.app.state.login_ip_rate_limiter.allow(client_ip)
    user_allowed = request.app.state.login_rate_limiter.allow(f"{client_ip}:{username}")
    if not (ip_allowed and user_allowed):
        return HTMLResponse(
            "<h1>429 Too Many Requests — try again later</h1>", status_code=429
        )

    user_store = request.app.state.container.get(UserStorePort)  # type: ignore[type-abstract]
    auth_codes = request.app.state.container.get(AuthCodeStorePort)  # type: ignore[type-abstract]
    hasher = request.app.state.container.get(PasswordHasherPort)  # type: ignore[type-abstract]

    user = await user_store.get_user_by_username(username)

    # bcrypt is CPU-bound — run in executor to avoid blocking the event loop.
    # The hasher verifies unknown users (hashed=None) against a dummy hash so
    # response timing does not reveal whether the username exists.
    loop = asyncio.get_running_loop()
    password_ok = await loop.run_in_executor(
        None,
        hasher.verify_password,
        password,
        user.password_hash if user is not None else None,
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
    client_ip = request.client.host if request.client else "unknown"
    if not request.app.state.token_rate_limiter.allow(client_ip):
        return _oauth_error("rate_limited", "Too many token requests", status=429)

    token_issuer = request.app.state.container.get(TokenIssuerPort)  # type: ignore[type-abstract]
    user_store = request.app.state.container.get(UserStorePort)  # type: ignore[type-abstract]
    auth_codes = request.app.state.container.get(AuthCodeStorePort)  # type: ignore[type-abstract]
    settings: Settings = request.app.state.settings

    if grant_type == "authorization_code":
        return await _handle_code_exchange(
            code=code,
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
            client_id=client_id,
            auth_codes=auth_codes,
            token_issuer=token_issuer,
            user_store=user_store,
            settings=settings,
        )

    if grant_type == "refresh_token":
        return await _handle_refresh(
            refresh_token=refresh_token,
            token_issuer=token_issuer,
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
    auth_codes: AuthCodeStorePort,
    token_issuer: TokenIssuerPort,
    user_store: UserStorePort,
    settings: Settings,
) -> JSONResponse:
    if not code or not code_verifier or not redirect_uri or not client_id:
        return _oauth_error(
            "invalid_request",
            "code, code_verifier, redirect_uri and client_id are required",
        )

    # Validate all claims against the stored entry BEFORE consuming it.
    # This prevents a mismatched redirect_uri or client_id from permanently
    # consuming the code and locking out the legitimate client.
    entry = await auth_codes.lookup(code)
    if entry is None:
        return _oauth_error("invalid_grant", "Authorization code invalid or expired")

    if entry.redirect_uri != redirect_uri:
        return _oauth_error("invalid_grant", "redirect_uri mismatch")

    if entry.client_id != client_id:
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
        token_issuer=token_issuer,
        user_store=user_store,
        settings=settings,
    )


async def _handle_refresh(
    *,
    refresh_token: str | None,
    token_issuer: TokenIssuerPort,
    user_store: UserStorePort,
    settings: Settings,
) -> JSONResponse:
    if not refresh_token:
        return _oauth_error("invalid_request", "refresh_token is required")

    # Atomic check-and-revoke — prevents concurrent requests from both succeeding
    user_id = await user_store.pop_refresh_token(refresh_token)
    if user_id is None:
        return _oauth_error("invalid_grant", "Refresh token invalid or expired")

    return await _issue_token_pair(
        user_id=user_id,
        token_issuer=token_issuer,
        user_store=user_store,
        settings=settings,
    )


async def _issue_token_pair(
    *,
    user_id: str,
    token_issuer: TokenIssuerPort,
    user_store: UserStorePort,
    settings: Settings,
) -> JSONResponse:
    access_token, expires_in = token_issuer.issue_access_token(user_id)
    new_refresh_token = token_issuer.issue_refresh_token()

    refresh_expire_days = settings.jwt_refresh_token_expire_days
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
