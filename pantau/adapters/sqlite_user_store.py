"""Adapter: SQLite-backed user and refresh-token store.

Tables created on start(); implements Lifecycle so the connection is managed
through the FastAPI lifespan.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from pantau.ports.user_store_port import UserRecord

log = logging.getLogger(__name__)

_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    username    TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
)
"""

_CREATE_REFRESH_TOKENS = """
CREATE TABLE IF NOT EXISTS refresh_tokens (
    token       TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    expires_at  TEXT NOT NULL
)
"""


class SqliteUserStore:
    """Persistent user store backed by SQLite via aiosqlite."""

    def __init__(self, db_path: str | Path = "pantau_users.db") -> None:
        self._db_path = str(db_path)
        self._conn: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle (matches composition.Lifecycle protocol)
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute(_CREATE_USERS)
        await self._conn.execute(_CREATE_REFRESH_TOKENS)
        await self._conn.commit()
        log.info("SqliteUserStore started (db=%s)", self._db_path)

    async def stop(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
        log.debug("SqliteUserStore stopped")

    # ------------------------------------------------------------------
    # UserStorePort implementation
    # ------------------------------------------------------------------

    async def get_user_by_username(self, username: str) -> UserRecord | None:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return UserRecord(
            id=row["id"], username=row["username"], password_hash=row["password_hash"]
        )

    async def create_user(self, username: str, password_hash: str) -> UserRecord:
        conn = self._require_conn()
        user_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, username, password_hash),
        )
        await conn.commit()
        log.info("Created user: %s", username)
        return UserRecord(id=user_id, username=username, password_hash=password_hash)

    async def save_refresh_token(
        self, token: str, user_id: str, expires_at: datetime
    ) -> None:
        conn = self._require_conn()
        await conn.execute(
            "INSERT OR REPLACE INTO refresh_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at.isoformat()),
        )
        await conn.commit()

    async def get_refresh_token_user_id(self, token: str) -> str | None:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT user_id, expires_at FROM refresh_tokens WHERE token = ?",
            (token,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if datetime.now(UTC) > expires_at:
            await self.revoke_refresh_token(token)
            return None
        return str(row["user_id"])

    async def revoke_refresh_token(self, token: str) -> None:
        conn = self._require_conn()
        await conn.execute("DELETE FROM refresh_tokens WHERE token = ?", (token,))
        await conn.commit()

    async def pop_refresh_token(self, token: str) -> str | None:
        """Atomically validate and revoke a refresh token.

        Returns user_id if the token is valid and not expired, else None.
        The token is removed from the store on both success and expiry.
        """
        conn = self._require_conn()
        now_iso = datetime.now(UTC).isoformat()
        async with conn.execute(
            "DELETE FROM refresh_tokens WHERE token = ? AND expires_at > ? RETURNING user_id",
            (token, now_iso),
        ) as cursor:
            row = await cursor.fetchone()
        await conn.commit()
        return str(row["user_id"]) if row else None

    # ------------------------------------------------------------------
    # Admin operations — used by CLI, not required by UserStorePort
    # ------------------------------------------------------------------

    async def list_users(self) -> list[UserRecord]:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT id, username, password_hash FROM users ORDER BY username"
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            UserRecord(
                id=r["id"], username=r["username"], password_hash=r["password_hash"]
            )
            for r in rows
        ]

    async def delete_user(self, username: str) -> bool:
        """Delete user and all their refresh tokens. Returns True if the user existed."""
        conn = self._require_conn()
        async with conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return False
        user_id = row["id"]
        await conn.execute("DELETE FROM refresh_tokens WHERE user_id = ?", (user_id,))
        await conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await conn.commit()
        log.info("Deleted user: %s", username)
        return True

    async def update_password(self, username: str, new_hash: str) -> bool:
        """Update password hash. Returns True if the user existed."""
        conn = self._require_conn()
        cursor = await conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (new_hash, username),
        )
        await conn.commit()
        updated = cursor.rowcount > 0
        if updated:
            log.info("Password updated for user: %s", username)
        return updated

    # ------------------------------------------------------------------

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("SqliteUserStore.start() was not called")
        return self._conn
