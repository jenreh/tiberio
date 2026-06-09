"""Tests for the pantau-users CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from pantau.adapters.sqlite_user_store import SqliteUserStore
from pantau.cli.users import app
from pantau.interfaces.oauth.router import hash_password

runner = CliRunner()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_users.db"


@pytest.fixture
async def populated_store(db_path: Path) -> SqliteUserStore:
    store = SqliteUserStore(db_path)
    await store.start()
    await store.create_user("alice", hash_password("password1"))
    await store.create_user("bob", hash_password("password2"))
    yield store
    await store.stop()


class TestAddCommand:
    def test_add_user_with_password_option(self, db_path: Path) -> None:
        result = runner.invoke(
            app, ["add", "testuser", "--db", str(db_path), "--password", "secret123"]
        )
        assert result.exit_code == 0
        assert "testuser" in result.output

    def test_add_duplicate_user_fails(self, db_path: Path) -> None:
        runner.invoke(app, ["add", "alice", "--db", str(db_path), "--password", "pw"])
        result = runner.invoke(
            app, ["add", "alice", "--db", str(db_path), "--password", "pw2"]
        )
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_add_user_shows_id(self, db_path: Path) -> None:
        result = runner.invoke(
            app, ["add", "newuser", "--db", str(db_path), "--password", "pw"]
        )
        assert "id=" in result.output

    def test_add_user_is_persisted(self, db_path: Path) -> None:
        runner.invoke(app, ["add", "carol", "--db", str(db_path), "--password", "pw"])
        result = runner.invoke(app, ["list", "--db", str(db_path)])
        assert "carol" in result.output


class TestListCommand:
    def test_list_empty_db(self, db_path: Path) -> None:
        result = runner.invoke(app, ["list", "--db", str(db_path)])
        assert result.exit_code == 0
        assert "No users" in result.output

    def test_list_shows_all_users(
        self, db_path: Path, populated_store: SqliteUserStore
    ) -> None:
        result = runner.invoke(app, ["list", "--db", str(db_path)])
        assert result.exit_code == 0
        assert "alice" in result.output
        assert "bob" in result.output

    def test_list_shows_header(
        self, db_path: Path, populated_store: SqliteUserStore
    ) -> None:
        result = runner.invoke(app, ["list", "--db", str(db_path)])
        assert "USERNAME" in result.output
        assert "ID" in result.output


class TestDeleteCommand:
    def test_delete_existing_user_with_yes_flag(
        self, db_path: Path, populated_store: SqliteUserStore
    ) -> None:
        result = runner.invoke(app, ["delete", "alice", "--db", str(db_path), "--yes"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_deleted_user_no_longer_listed(
        self, db_path: Path, populated_store: SqliteUserStore
    ) -> None:
        runner.invoke(app, ["delete", "alice", "--db", str(db_path), "--yes"])
        result = runner.invoke(app, ["list", "--db", str(db_path)])
        assert "alice" not in result.output
        assert "bob" in result.output

    def test_delete_nonexistent_user_fails(self, db_path: Path) -> None:
        result = runner.invoke(app, ["delete", "nobody", "--db", str(db_path), "--yes"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_delete_prompts_without_yes_flag(
        self, db_path: Path, populated_store: SqliteUserStore
    ) -> None:
        result = runner.invoke(
            app, ["delete", "alice", "--db", str(db_path)], input="y\n"
        )
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_delete_aborted_when_declined(
        self, db_path: Path, populated_store: SqliteUserStore
    ) -> None:
        result = runner.invoke(
            app, ["delete", "alice", "--db", str(db_path)], input="n\n"
        )
        assert result.exit_code != 0
        # User still exists
        list_result = runner.invoke(app, ["list", "--db", str(db_path)])
        assert "alice" in list_result.output


class TestPasswdCommand:
    def test_passwd_updates_password(
        self, db_path: Path, populated_store: SqliteUserStore
    ) -> None:
        result = runner.invoke(
            app, ["passwd", "alice", "--db", str(db_path), "--password", "newpw"]
        )
        assert result.exit_code == 0
        assert "updated" in result.output

    def test_passwd_nonexistent_user_fails(self, db_path: Path) -> None:
        result = runner.invoke(
            app, ["passwd", "nobody", "--db", str(db_path), "--password", "pw"]
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_new_password_is_accepted_for_login(
        self, db_path: Path, populated_store: SqliteUserStore
    ) -> None:
        import bcrypt

        runner.invoke(
            app, ["passwd", "alice", "--db", str(db_path), "--password", "brand-new-pw"]
        )
        store = SqliteUserStore(db_path)

        async def _check() -> None:
            await store.start()
            user = await store.get_user_by_username("alice")
            await store.stop()
            assert user is not None
            assert bcrypt.checkpw(b"brand-new-pw", user.password_hash.encode())

        import asyncio

        asyncio.run(_check())


class TestAdminStoreOperations:
    """Direct tests for SqliteUserStore admin methods."""

    async def test_list_users_returns_all(self, db_path: Path) -> None:
        store = SqliteUserStore(db_path)
        await store.start()
        await store.create_user("u1", "h1")
        await store.create_user("u2", "h2")
        users = await store.list_users()
        await store.stop()
        assert len(users) == 2
        assert {u.username for u in users} == {"u1", "u2"}

    async def test_list_users_ordered_alphabetically(self, db_path: Path) -> None:
        store = SqliteUserStore(db_path)
        await store.start()
        await store.create_user("zebra", "h")
        await store.create_user("apple", "h")
        users = await store.list_users()
        await store.stop()
        assert [u.username for u in users] == ["apple", "zebra"]

    async def test_delete_user_removes_refresh_tokens(self, db_path: Path) -> None:
        from datetime import UTC, datetime, timedelta

        store = SqliteUserStore(db_path)
        await store.start()
        user = await store.create_user("dave", "h")
        expires = datetime.now(UTC) + timedelta(days=30)
        await store.save_refresh_token("tok-1", user.id, expires)

        await store.delete_user("dave")
        user_id = await store.get_refresh_token_user_id("tok-1")
        await store.stop()
        assert user_id is None

    async def test_update_password_returns_false_for_unknown_user(
        self, db_path: Path
    ) -> None:
        store = SqliteUserStore(db_path)
        await store.start()
        result = await store.update_password("nobody", "hash")
        await store.stop()
        assert result is False
