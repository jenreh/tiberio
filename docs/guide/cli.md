# CLI Reference

pantau-alexa ships three executables, all installed by `uv sync`:

| Command | Purpose |
|---|---|
| `pantau` | Start the FastAPI home automation server |
| `pantau-users` | Manage user accounts in the SQLite database |
| `pantau-beacon` | Publish the S3 endpoint beacon (current tunnel URL) |

---

## pantau — start the server

```bash
uv run pantau
```

Reads all settings from environment variables / `.env` and starts Uvicorn. There are no CLI flags — everything is controlled via [environment variables](./configuration#environment-variables).

The server binds to `HOST:PORT` (default `0.0.0.0:8080`) and runs until interrupted.

```bash
# Run on a custom port
PORT=9000 uv run pantau

# Run in debug mode (auto-reload on code changes)
DEBUG=true uv run pantau
```

**What happens at startup:**
1. Settings are loaded from `.env` / environment.
2. `build_container()` wires all ports to their adapters.
3. FastAPI lifespan calls `start()` on lifecycle adapters:
   - `HarmonyTvAdapter` opens the Harmony Hub WebSocket.
   - `SqliteUserStore` opens the database connection and creates tables if they don't exist.
4. Routes are registered: `/alexa/directive`, `/oauth/*`, `/health`.
5. Uvicorn starts accepting requests.

---

## pantau-users — manage user accounts

The OAuth2 login form requires at least one user in the database. Use `pantau-users` to manage those accounts.

All subcommands accept a `--db` option to specify the SQLite database path. If omitted, the path is read from the `USERS_DB_PATH` environment variable or the default (`pantau_users.db`).

### add — create a new user

```bash
pantau-users add USERNAME [--db PATH] [--password PASSWORD]
```

```bash
# Interactive (prompted for password with confirmation)
uv run pantau-users add alice

# Non-interactive (for scripts)
uv run pantau-users add alice --password "s3cr3t"

# Use a specific database file
uv run pantau-users add alice --db /var/lib/pantau/users.db
```

- Exits with code `1` if the username already exists.
- The password is bcrypt-hashed before storage — the plain text is never written anywhere.

**Example output:**

```
Password: ********
Repeat for confirmation: ********
Created user 'alice' (id=3f2504e0-4f89-11d3-9a0c-0305e82c3301)
```

---

### list — show all users

```bash
pantau-users list [--db PATH]
```

```bash
uv run pantau-users list
```

**Example output:**

```
USERNAME    ID
-------------------------------------------------------
alice       3f2504e0-4f89-11d3-9a0c-0305e82c3301
bob         7c9e6679-7425-40de-944b-e07fc1f90ae7
```

---

### delete — remove a user

```bash
pantau-users delete USERNAME [--db PATH] [--yes]
```

```bash
# With confirmation prompt (default)
uv run pantau-users delete alice

# Skip confirmation (useful in scripts)
uv run pantau-users delete alice --yes
uv run pantau-users delete alice -y
```

Deletes the user record **and** revokes all their active refresh tokens. The next directive from Alexa will fail with 401 until Account Linking is re-done.

- Exits with code `1` if the user does not exist.

**Example output:**

```
Delete user 'alice' and revoke all their tokens? [y/N]: y
Deleted user 'alice'.
```

---

### passwd — change a password

```bash
pantau-users passwd USERNAME [--db PATH] [--password NEW_PASSWORD]
```

```bash
# Interactive (prompted)
uv run pantau-users passwd alice

# Non-interactive
uv run pantau-users passwd alice --password "newS3cr3t"
uv run pantau-users passwd alice -p "newS3cr3t"
```

Updates the bcrypt hash for the user. Does **not** revoke existing tokens — active sessions remain valid until their JWTs expire.

- Exits with code `1` if the user does not exist.

---

## pantau-beacon — publish the endpoint beacon

The AWS edge resolves the home server's address from `endpoint.json` in the S3
beacon bucket. `pantau-beacon publish` writes that object with the current
public base URL. The server also publishes it automatically at startup and on
an interval (when `PANTAU_BEACON_ENABLED=true`); use the CLI to publish on
demand — for example from a tunnel hook when the URL rotates.

```
pantau-beacon publish [--base-url URL] [--bucket NAME] [--key KEY] [--region REGION]
```

```bash
# Explicit URL
uv run pantau-beacon publish --base-url https://your-tunnel.example.com

# Fall back to PANTAU_PUBLIC_BASE_URL and the configured bucket/key/region
uv run pantau-beacon publish
```

Each option defaults to the corresponding setting (`PANTAU_PUBLIC_BASE_URL`,
`PANTAU_S3_BEACON_BUCKET`, `PANTAU_S3_BEACON_KEY`, `PANTAU_AWS_REGION`).

- Exits with code `1` if no base URL is given (neither `--base-url` nor
  `PANTAU_PUBLIC_BASE_URL`) or if the S3 write fails.

---

## Common --db option

All `pantau-users` subcommands resolve the database path in this order:

1. `--db PATH` flag
2. `USERS_DB_PATH` environment variable
3. Default: `pantau_users.db` (in the current directory)

This makes it easy to point the CLI at the same database the server uses:

```bash
export USERS_DB_PATH=/var/lib/pantau/users.db
uv run pantau-users list
uv run pantau-users add alice
```

---

## Quick-start example

First-time setup from scratch:

```bash
# 1. Create a .env file with required secrets
echo 'JWT_SECRET=your-long-secret-here' >> .env
echo 'USERS_DB_PATH=pantau_users.db' >> .env

# 2. Create the first user (the server must NOT be running yet;
#    the CLI opens its own database connection)
uv run pantau-users add alice

# 3. Start the server (creates the DB and tables if not present)
uv run pantau

# 4. Verify
curl http://localhost:8080/health
```

::: tip Database on first run
`SqliteUserStore` creates both tables (`users`, `refresh_tokens`) automatically when `start()` is called — either by the server lifespan or by the CLI for each command. You never need to run migrations manually.
:::
