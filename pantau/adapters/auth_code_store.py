"""In-memory store for short-lived OAuth2 authorization codes (PKCE).

Auth codes expire in 5 minutes — well within the RFC 6749 10-minute maximum.
The single-process, single-household deployment makes in-memory storage safe.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

log = logging.getLogger(__name__)

_CODE_TTL_SECONDS = 300  # 5 minutes


@dataclass(slots=True)
class AuthCodeEntry:
    code: str
    user_id: str
    client_id: str
    redirect_uri: str
    code_challenge: str
    code_challenge_method: str
    expires_at: datetime


class AuthCodeStore:
    """Thread-safe in-memory store for PKCE authorization codes."""

    def __init__(self) -> None:
        self._codes: dict[str, AuthCodeEntry] = {}
        self._lock = asyncio.Lock()

    def generate_code(self) -> str:
        return secrets.token_urlsafe(32)

    async def save(
        self,
        *,
        user_id: str,
        client_id: str,
        redirect_uri: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> str:
        code = self.generate_code()
        entry = AuthCodeEntry(
            code=code,
            user_id=user_id,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            expires_at=datetime.now(UTC) + timedelta(seconds=_CODE_TTL_SECONDS),
        )
        async with self._lock:
            self._codes[code] = entry
        log.debug("Auth code saved for user %s", user_id)
        return code

    async def lookup(self, code: str) -> AuthCodeEntry | None:
        """Return the entry without consuming it, or None if absent/expired.

        Expired entries are removed from the store to prevent unbounded growth.
        """
        async with self._lock:
            entry = self._codes.get(code)
            if entry is not None and datetime.now(UTC) > entry.expires_at:
                self._codes.pop(code, None)
                log.warning("Auth code expired for user %s", entry.user_id)
                entry = None
        return entry

    async def redeem(self, code: str) -> AuthCodeEntry | None:
        """Atomically consume and return the entry, or None if absent/expired."""
        async with self._lock:
            entry = self._codes.pop(code, None)
        if entry is None:
            return None
        if datetime.now(UTC) > entry.expires_at:
            log.warning("Auth code expired for user %s", entry.user_id)
            return None
        return entry
