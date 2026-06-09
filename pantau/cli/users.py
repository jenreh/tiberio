"""pantau-users — CLI for managing pantau-alexa user accounts.

Commands:
  add     Add a new user
  list    List all users
  delete  Delete a user (and revoke their tokens)
  passwd  Change a user's password
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from pantau.adapters.sqlite_user_store import SqliteUserStore
from pantau.interfaces.oauth.router import hash_password

app = typer.Typer(
    name="pantau-users",
    help="Manage pantau-alexa user accounts.",
    no_args_is_help=True,
)


def _resolve_db(db: Path | None) -> Path:
    if db is not None:
        return db
    try:
        from pantau.config.settings import get_settings

        return get_settings().users_db_path
    except Exception:  # pragma: no cover
        return Path("pantau_users.db")


def _run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


@app.command()
def add(
    username: Annotated[str, typer.Argument(help="Username to create")],
    db: Annotated[
        Path | None,
        typer.Option(
            "--db", help="SQLite DB path", envvar="USERS_DB_PATH", show_default=False
        ),
    ] = None,
    password: Annotated[
        str | None,
        typer.Option(
            "--password", "-p", help="Password (prompted if omitted)", hide_input=True
        ),
    ] = None,
) -> None:
    """Add a new user account."""
    if password is None:
        password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)

    async def _create() -> None:
        store = SqliteUserStore(_resolve_db(db))
        await store.start()
        try:
            existing = await store.get_user_by_username(username)
            if existing is not None:
                typer.echo(f"Error: user '{username}' already exists.", err=True)
                raise typer.Exit(1)
            hashed = hash_password(password)  # type: ignore[arg-type]
            user = await store.create_user(username, hashed)
            typer.echo(f"Created user '{user.username}' (id={user.id})")
        finally:
            await store.stop()

    _run(_create())


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@app.command(name="list")
def list_users(
    db: Annotated[
        Path | None,
        typer.Option(
            "--db", help="SQLite DB path", envvar="USERS_DB_PATH", show_default=False
        ),
    ] = None,
) -> None:
    """List all user accounts."""

    async def _list() -> None:
        store = SqliteUserStore(_resolve_db(db))
        await store.start()
        try:
            users = await store.list_users()
        finally:
            await store.stop()

        if not users:
            typer.echo("No users found.")
            return

        col_w = max(len(u.username) for u in users) + 2
        typer.echo(f"{'USERNAME':<{col_w}}  ID")
        typer.echo("-" * (col_w + 38))
        for u in users:
            typer.echo(f"{u.username:<{col_w}}  {u.id}")

    _run(_list())


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@app.command()
def delete(
    username: Annotated[str, typer.Argument(help="Username to delete")],
    db: Annotated[
        Path | None,
        typer.Option(
            "--db", help="SQLite DB path", envvar="USERS_DB_PATH", show_default=False
        ),
    ] = None,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip confirmation prompt")
    ] = False,
) -> None:
    """Delete a user account and revoke all their tokens."""
    if not yes:
        typer.confirm(
            f"Delete user '{username}' and revoke all their tokens?", abort=True
        )

    async def _delete() -> None:
        store = SqliteUserStore(_resolve_db(db))
        await store.start()
        try:
            removed = await store.delete_user(username)
        finally:
            await store.stop()

        if removed:
            typer.echo(f"Deleted user '{username}'.")
        else:
            typer.echo(f"Error: user '{username}' not found.", err=True)
            raise typer.Exit(1)

    _run(_delete())


# ---------------------------------------------------------------------------
# passwd
# ---------------------------------------------------------------------------


@app.command()
def passwd(
    username: Annotated[str, typer.Argument(help="Username whose password to change")],
    db: Annotated[
        Path | None,
        typer.Option(
            "--db", help="SQLite DB path", envvar="USERS_DB_PATH", show_default=False
        ),
    ] = None,
    new_password: Annotated[
        str | None,
        typer.Option(
            "--password",
            "-p",
            help="New password (prompted if omitted)",
            hide_input=True,
        ),
    ] = None,
) -> None:
    """Change a user's password."""
    if new_password is None:
        new_password = typer.prompt(
            "New password", hide_input=True, confirmation_prompt=True
        )

    async def _passwd() -> None:
        store = SqliteUserStore(_resolve_db(db))
        await store.start()
        try:
            hashed = hash_password(new_password)  # type: ignore[arg-type]
            updated = await store.update_password(username, hashed)
        finally:
            await store.stop()

        if updated:
            typer.echo(f"Password updated for '{username}'.")
        else:
            typer.echo(f"Error: user '{username}' not found.", err=True)
            raise typer.Exit(1)

    _run(_passwd())


def main() -> None:  # pragma: no cover
    app()
