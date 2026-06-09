# interfaces/oauth/

**Location:** `pantau/interfaces/oauth/router.py`  
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
- `code_challenge_method` — `S256` (or `plain`)
- `state` — CSRF token from Alexa
- `response_type` — always `code`

The handler validates that `redirect_uri` is in the `OAUTH_ALLOWED_REDIRECT_URIS` allowlist. In dev mode (empty allowlist), any URI is accepted with a warning log.

All query parameters are embedded as hidden form fields, then HTML-escaped before rendering to prevent XSS.

---

## POST /oauth/authorize

Validates credentials and issues an authorization code. Form fields mirror the hidden fields from the GET step.

```python
# 1. Validate redirect_uri against allowlist
# 2. Look up user by username
user = await user_store.get_user_by_username(username)

# 3. Verify password with bcrypt
if user is None or not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
    # Re-render login form with error message

# 4. Save authorization code entry (with PKCE challenge)
code = await auth_codes.save(
    user_id=user.id,
    client_id=client_id,
    redirect_uri=redirect_uri,
    code_challenge=code_challenge,
    code_challenge_method=code_challenge_method,
)

# 5. Redirect back to Alexa with ?code=…&state=…
return RedirectResponse(f"{redirect_uri}?code={code}&state={state}", status_code=302)
```

---

## POST /oauth/token

Handles two grant types:

### authorization_code grant

Alexa calls this to exchange the short-lived auth code for a long-lived token pair.

```
grant_type=authorization_code
code=<the code from the redirect>
code_verifier=<the plain text that was hashed to produce code_challenge>
redirect_uri=<must match the one used in authorize>
```

**Steps:**
1. Redeem the code (atomically deletes it — single-use).
2. Verify `redirect_uri` matches the saved one.
3. Verify PKCE: `BASE64URL(SHA-256(code_verifier)) == code_challenge`.
4. Issue JWT access token + random refresh token.
5. Store refresh token in SQLite with expiry.

### refresh_token grant

Alexa calls this automatically when the access token expires.

```
grant_type=refresh_token
refresh_token=<the opaque token from a previous response>
```

**Steps:**
1. Look up `refresh_token` in SQLite (checks expiry).
2. Revoke the old token (rotation — one-time use).
3. Issue a new JWT + new refresh token.
4. Return the new pair.

---

## Token issuance

Both grant paths call the same internal helper:

```python
async def _issue_token_pair(user_id, jwt_service, user_store, settings) -> JSONResponse:
    access_token, expires_in = jwt_service.issue_access_token(user_id)
    new_refresh_token = jwt_service.issue_refresh_token()

    await user_store.save_refresh_token(
        new_refresh_token, user_id,
        expires_at=datetime.now(UTC) + timedelta(days=30)
    )

    return JSONResponse({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,         # seconds (e.g. 3600)
        "refresh_token": new_refresh_token,
    })
```

---

## PKCE verification

```python
def _verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    if method == "S256":
        digest = hashlib.sha256(code_verifier.encode()).digest()
        computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        return secrets.compare_digest(computed, code_challenge)
    if method == "plain":
        return secrets.compare_digest(code_verifier, code_challenge)
    return False
```

`secrets.compare_digest` is used instead of `==` to prevent timing attacks.

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
| `invalid_request` | Missing required parameter |
| `invalid_grant` | Code invalid/expired, PKCE mismatch, redirect_uri mismatch, refresh token invalid |
| `unsupported_grant_type` | Unknown `grant_type` |

---

## Security summary

| Threat | Mitigation |
|---|---|
| Password brute force | bcrypt (slow hash); HTTP 401 on failure |
| Authorization code replay | Codes are atomically deleted on first use |
| PKCE bypass | SHA-256 hash comparison using `secrets.compare_digest` |
| Redirect URI hijacking | `OAUTH_ALLOWED_REDIRECT_URIS` allowlist |
| XSS in login form | All user-controlled values HTML-escaped before rendering |
| Stolen refresh token | Token rotation — each token is single-use |
| Expired access token | Short expiry (60 min) + automatic Alexa refresh |
| Timing attacks | `secrets.compare_digest` for PKCE and password hash comparison |
