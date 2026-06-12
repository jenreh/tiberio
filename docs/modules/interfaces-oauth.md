# interfaces/oauth/

**Location:** `tiberio/interfaces/oauth/router.py`
**Rule:** All user-controlled input is HTML-escaped. OAuth errors follow RFC 6749 format. No secret values in logs.

The OAuth interface implements a minimal **Authorization Code Grant with PKCE** — just enough to satisfy Alexa's Account Linking requirements. It is self-contained in a single file.

## Why a custom OAuth server?

Alexa's Account Linking requires the home server to have a stable, public OAuth2 authorization and token endpoint. The home server *is* the Identity Provider — users log in directly to their home server, not to a third-party auth service. This gives full control over credentials and tokens, with no dependency on external services.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/oauth/authorize` | Show HTML login form |
| `POST` | `/oauth/authorize` | Validate credentials; issue auth code; redirect |
| `POST` | `/oauth/token` | Exchange code → tokens, or rotate refresh token |

---

## GET /oauth/authorize

Shows the HTML login form. Alexa (or its OAuth browser) redirects to this URL at the start of Account Linking.

**Query parameters (from Alexa):**
- `client_id` — Alexa's client identifier
- `redirect_uri` — URL Alexa will poll for the authorization code
- `code_challenge` — PKCE challenge (SHA-256 hash of `code_verifier`)
- `code_challenge_method` — must be `S256` (anything else, including `plain`, is rejected with HTTP 400)
- `state` — CSRF token from Alexa
- `response_type` — must be `code` (any other value is rejected with HTTP 400, `unsupported_response_type`)

The handler validates that `redirect_uri` is in the `TIBERIO_OAUTH_ALLOWED_REDIRECT_URIS` allowlist. With an empty allowlist the behavior is fail-closed: in dev mode (`TIBERIO_DEV_MODE`) any URI is accepted with a warning log; otherwise the endpoint returns 503 (OAuth not configured).

All query parameters are embedded as hidden form fields, then HTML-escaped before rendering to prevent XSS.

---

## POST /oauth/authorize

Validates credentials and issues an authorization code. Form fields mirror the hidden fields from the GET step. `code_challenge_method` is re-checked here — only `S256` is accepted.

Before any credential check, the request must pass **two rate-limit buckets** (see below); otherwise HTTP 429 is returned.

```python
# 1. Validate redirect_uri against allowlist; reject non-S256 PKCE methods
# 2. Check rate limits (per-IP and per-IP+username) → 429 if exceeded
# 3. Look up user and verify password via PasswordHasherPort
user = await user_store.get_user_by_username(username)
password_ok = await loop.run_in_executor(
    None,
    hasher.verify_password,
    password,
    user.password_hash if user is not None else None,
)
if not password_ok:
    # Re-render login form with error message (HTTP 401)

# 4. Save authorization code entry (with PKCE challenge + client_id binding)
code = await auth_codes.save(
    user_id=user.id,
    client_id=client_id,
    redirect_uri=redirect_uri,
    code_challenge=code_challenge,
    code_challenge_method=code_challenge_method,
)

# 5. Redirect back to Alexa with ?code=…&state=…
return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=302)
```

Password verification goes through `PasswordHasherPort` (implemented by `BcryptPasswordHasher`). bcrypt is CPU-bound, so it runs in an executor to avoid blocking the event loop. For an **unknown username** the hasher is still called with `hashed=None` and verifies against a dummy hash with the same cost factor — response timing does not reveal whether the username exists.

---

## POST /oauth/token

Rate-limited per client IP (HTTP 429 with `"error": "rate_limited"` when exceeded). Handles two grant types:

### authorization_code grant

Alexa calls this to exchange the short-lived auth code for a long-lived token pair.

```
grant_type=authorization_code
code=<the code from the redirect>
code_verifier=<the plain text that was hashed to produce code_challenge>
redirect_uri=<must match the one used in authorize>
client_id=<must match the one used in authorize>
```

`code`, `code_verifier`, `redirect_uri` **and `client_id`** are all required — a missing `client_id` is an `invalid_request` error.

**Steps:**
1. Look up the code (`lookup()` — not yet consumed).
2. Verify `redirect_uri` matches the saved one.
3. Verify `client_id` matches the saved one.
4. Verify PKCE: `BASE64URL(SHA-256(code_verifier)) == code_challenge`.
5. Atomically redeem the code (single-use; guards against concurrent requests).
6. Issue JWT access token + random refresh token.
7. Store the refresh token (SHA-256-hashed) in SQLite with expiry.

All claims are validated **before** the code is consumed — a mismatched `redirect_uri` or `client_id` must not permanently burn the code and lock out the legitimate client.

### refresh_token grant

Alexa calls this automatically when the access token expires.

```
grant_type=refresh_token
refresh_token=<the opaque token from a previous response>
```

**Steps:**
1. `pop_refresh_token()` — atomic check-and-revoke in SQLite (validates expiry, deletes the token, returns the user ID). Concurrent requests with the same token cannot both succeed.
2. Issue a new JWT + new refresh token (rotation — one-time use).
3. Return the new pair.

---

## Token issuance

`token_post` dispatches on `grant_type` to one of two module-level handlers — `_handle_code_exchange` and `_handle_refresh` — and both delegate to the same internal helper, `_issue_token_pair`:

```python
async def _issue_token_pair(
    *, user_id, token_issuer, user_store, settings
) -> JSONResponse:
    access_token, expires_in = token_issuer.issue_access_token(user_id)
    new_refresh_token = token_issuer.issue_refresh_token()

    expires_at = datetime.now(UTC) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
    await user_store.save_refresh_token(new_refresh_token, user_id, expires_at)

    return JSONResponse({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,         # seconds (e.g. 3600)
        "refresh_token": new_refresh_token,
    })
```

The plain refresh token is returned to the client only; `SqliteUserStore` persists it **SHA-256-hashed**, so a leaked database does not expose usable tokens.

---

## PKCE verification

```python
def _verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    # Only S256 is accepted; 'plain' would downgrade PKCE to a bearer secret.
    if method == "S256":
        digest = hashlib.sha256(code_verifier.encode()).digest()
        computed = urlsafe_b64encode(digest).rstrip(b"=").decode()
        return secrets.compare_digest(computed, code_challenge)
    return False
```

`secrets.compare_digest` is used instead of `==` to prevent timing attacks. The `plain` method is deliberately not implemented: it would reduce PKCE to a static shared secret. (It is already rejected with HTTP 400 at `/oauth/authorize`, so verification can never see it for codes issued by this server.)

---

## Rate limiting

**File:** `tiberio/interfaces/rate_limit.py`

`SlidingWindowRateLimiter` is an in-memory sliding-window limiter ("at most *max_attempts* events per *window_seconds* per key"). Three instances are created on `app.state` at startup:

| Limiter | Key | Limit |
|---|---|---|
| `login_rate_limiter` | `"{client_ip}:{username}"` | `rate_limit_max_attempts` per window |
| `login_ip_rate_limiter` | client IP | `rate_limit_max_attempts * 3` per window |
| `token_rate_limiter` | client IP | `rate_limit_max_attempts` per window |

`POST /oauth/authorize` must pass both login buckets (slows brute force against one account *and* spraying many accounts from one IP); `POST /oauth/token` uses the per-IP token bucket. Exceeding a limit returns HTTP 429. Defaults: 10 attempts per 60 seconds (`rate_limit_max_attempts`, `rate_limit_window_seconds`). Single-process only — a multi-worker setup would need a shared backend.

To bound memory under key churn (e.g. IP/username spraying), the limiter prunes expired keys via `_drop_expired` once the tracked-key count exceeds `_CLEANUP_THRESHOLD` (10,000). This is an internal guard only and does not change the per-key limit behavior.

---

## Error responses

All errors follow RFC 6749 format:

```json
{
  "error": "invalid_grant",
  "error_description": "Authorization code invalid or expired"
}
```

| Error code | When |
|---|---|
| `invalid_request` | Missing required parameter (incl. `client_id`) |
| `invalid_grant` | Code invalid/expired/used, PKCE mismatch, redirect_uri mismatch, client_id mismatch, refresh token invalid |
| `unsupported_grant_type` | Unknown `grant_type` |
| `rate_limited` | Too many token requests (HTTP 429) |

---

## Security summary

| Threat | Mitigation |
|---|---|
| Password brute force | bcrypt (slow hash); HTTP 401 on failure; sliding-window rate limits (per-IP+username and per-IP) |
| Username enumeration via timing | `PasswordHasherPort` verifies unknown users against a dummy hash of equal cost |
| Authorization code replay | Codes are atomically redeemed on first use |
| Code theft across clients | `client_id` and `redirect_uri` bound to the code and re-verified at exchange |
| PKCE downgrade | Only `S256` accepted; `plain` rejected at authorize and verification |
| PKCE bypass | SHA-256 hash comparison using `secrets.compare_digest` |
| Redirect URI hijacking | `TIBERIO_OAUTH_ALLOWED_REDIRECT_URIS` allowlist (fail-closed outside dev mode) |
| XSS in login form | All user-controlled values HTML-escaped before rendering |
| Stolen refresh token | Token rotation (single-use, atomic pop); stored SHA-256-hashed |
| Token endpoint abuse | Per-IP rate limit, HTTP 429 |
| Expired access token | Short expiry (60 min) + automatic Alexa refresh |
| Timing attacks | `secrets.compare_digest` for PKCE; constant-cost password verification |
