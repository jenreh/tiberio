"""Tests for SqliteUserStore — user and refresh-token persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pantau.adapters.sqlite_user_store import SqliteUserStore


@pytest.fixture
async def store(tmp_path: Path) -> SqliteUserStore:
    s = SqliteUserStore(tmp_path / "test.db")
    await s.start()
    yield s
    await s.stop()


@pytest.fixture
async def memory_store() -> SqliteUserStore:
    s = SqliteUserStore(":memory:")
    await s.start()
    yield s
    await s.stop()


class TestCreateAndGetUser:
    async def test_create_user_returns_record(self, store: SqliteUserStore) -> None:
        user = await store.create_user("alice", "hash_abc")
        assert user.username == "alice"
        assert user.password_hash == "hash_abc"
        assert len(user.id) > 0

    async def test_get_existing_user(self, store: SqliteUserStore) -> None:
        await store.create_user("bob", "hash_xyz")
        user = await store.get_user_by_username("bob")
        assert user is not None
        assert user.username == "bob"

    async def test_get_unknown_user_returns_none(self, store: SqliteUserStore) -> None:
        result = await store.get_user_by_username("nobody")
        assert result is None

    async def test_user_id_is_unique(self, store: SqliteUserStore) -> None:
        u1 = await store.create_user("user1", "h1")
        u2 = await store.create_user("user2", "h2")
        assert u1.id != u2.id


class TestRefreshTokens:
    async def test_save_and_retrieve_refresh_token(
        self, store: SqliteUserStore
    ) -> None:
        user = await store.create_user("carol", "hash")
        expires = datetime.now(UTC) + timedelta(days=30)
        await store.save_refresh_token("token-abc", user.id, expires)

        user_id = await store.get_refresh_token_user_id("token-abc")
        assert user_id == user.id

    async def test_unknown_token_returns_none(self, store: SqliteUserStore) -> None:
        result = await store.get_refresh_token_user_id("nonexistent-token")
        assert result is None

    async def test_expired_token_returns_none(self, store: SqliteUserStore) -> None:
        user = await store.create_user("dave", "hash")
        past = datetime.now(UTC) - timedelta(seconds=1)
        await store.save_refresh_token("expired-token", user.id, past)

        result = await store.get_refresh_token_user_id("expired-token")
        assert result is None

    async def test_revoke_token(self, store: SqliteUserStore) -> None:
        user = await store.create_user("eve", "hash")
        expires = datetime.now(UTC) + timedelta(days=30)
        await store.save_refresh_token("revokeable", user.id, expires)

        await store.revoke_refresh_token("revokeable")
        result = await store.get_refresh_token_user_id("revokeable")
        assert result is None

    async def test_save_refresh_token_replaces_existing(
        self, store: SqliteUserStore
    ) -> None:
        user = await store.create_user("frank", "hash")
        expires = datetime.now(UTC) + timedelta(days=30)
        await store.save_refresh_token("same-token", user.id, expires)
        # Saving again should not raise
        await store.save_refresh_token("same-token", user.id, expires)
        user_id = await store.get_refresh_token_user_id("same-token")
        assert user_id == user.id


class TestPopRefreshToken:
    async def test_pop_returns_user_id_for_valid_token(
        self, store: SqliteUserStore
    ) -> None:
        user = await store.create_user("pop-alice", "hash")
        expires = datetime.now(UTC) + timedelta(days=30)
        await store.save_refresh_token("pop-token-1", user.id, expires)

        user_id = await store.pop_refresh_token("pop-token-1")
        assert user_id == user.id

    async def test_pop_removes_token(self, store: SqliteUserStore) -> None:
        user = await store.create_user("pop-bob", "hash")
        expires = datetime.now(UTC) + timedelta(days=30)
        await store.save_refresh_token("pop-token-2", user.id, expires)

        await store.pop_refresh_token("pop-token-2")
        assert await store.get_refresh_token_user_id("pop-token-2") is None

    async def test_pop_returns_none_for_expired_token(
        self, store: SqliteUserStore
    ) -> None:
        user = await store.create_user("pop-carol", "hash")
        past = datetime.now(UTC) - timedelta(seconds=1)
        await store.save_refresh_token("pop-expired", user.id, past)

        assert await store.pop_refresh_token("pop-expired") is None

    async def test_pop_returns_none_for_unknown_token(
        self, store: SqliteUserStore
    ) -> None:
        assert await store.pop_refresh_token("nonexistent-pop") is None

    async def test_pop_is_single_use(self, store: SqliteUserStore) -> None:
        user = await store.create_user("pop-dave", "hash")
        expires = datetime.now(UTC) + timedelta(days=30)
        await store.save_refresh_token("pop-one-time", user.id, expires)

        assert await store.pop_refresh_token("pop-one-time") == user.id
        assert await store.pop_refresh_token("pop-one-time") is None


class TestLifecycle:
    async def test_stop_and_restart(self, tmp_path: Path) -> None:
        """Data persists across stop/start cycles (file-based store)."""
        db_path = tmp_path / "persist.db"
        store = SqliteUserStore(db_path)
        await store.start()
        await store.create_user("grace", "hash")
        await store.stop()

        store2 = SqliteUserStore(db_path)
        await store2.start()
        user = await store2.get_user_by_username("grace")
        await store2.stop()

        assert user is not None
        assert user.username == "grace"

    async def test_requires_start_before_use(self, tmp_path: Path) -> None:
        store = SqliteUserStore(tmp_path / "unused.db")
        with pytest.raises(RuntimeError, match="start\\(\\)"):
            await store.get_user_by_username("nobody")

    async def test_in_memory_store(self, memory_store: SqliteUserStore) -> None:
        user = await memory_store.create_user("henry", "hash")
        found = await memory_store.get_user_by_username("henry")
        assert found is not None
        assert found.id == user.id
