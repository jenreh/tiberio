# CLI Reference

tiberio ships four executables, all installed by `uv sync`:

| Command | Purpose |
|---|---|
| `tiberio` | Start the FastAPI home automation server |
| `tiberio-users` | Manage user accounts in the SQLite database |
| `tiberio-beacon` | Publish the S3 endpoint beacon (current tunnel URL) |
| `tiberio-setup` | Deploy the AWS edge and wire up Alexa account linking |

---

## tiberio — start the server

```bash
uv run tiberio
```

Reads all settings from environment variables / `.env` and starts Uvicorn. There are no CLI flags — everything is controlled via [environment variables](./configuration#environment-variables).

The server binds to `TIBERIO_HOST:TIBERIO_PORT` (default `0.0.0.0:8080`) and runs until interrupted. All settings are read with the `TIBERIO_` prefix (see [`Settings`](./configuration#environment-variables)), so the env vars must be prefixed too.

```bash
# Run on a custom port
TIBERIO_PORT=9000 uv run tiberio

# Run in debug mode (auto-reload on code changes)
TIBERIO_DEBUG=true uv run tiberio
```

::: warning JWT secret is required
The server refuses to start unless `TIBERIO_JWT_SECRET` is set to a sufficiently long value (or `TIBERIO_DEV_MODE=true` for local development). An empty or short secret would make every access token forgeable.
:::

**What happens at startup:**
1. Settings are loaded from `.env` / environment.
2. `build_container()` wires all ports to their adapters.
3. FastAPI lifespan calls `start()` on lifecycle adapters:
   - `HarmonyTvAdapter` opens the Harmony Hub WebSocket.
   - `SqliteUserStore` opens the database connection and creates tables if they don't exist.
4. Routes are registered: `/alexa/directive`, `/oauth/*`, `/health`.
5. Uvicorn starts accepting requests.

---

## tiberio-users — manage user accounts

The OAuth2 login form requires at least one user in the database. Use `tiberio-users` to manage those accounts.

All subcommands accept a `--db` option to specify the SQLite database path. If omitted, the path falls back to the `USERS_DB_PATH` environment variable (the CLI's own Typer `envvar`), then to the server setting `TIBERIO_USERS_DB_PATH`, and finally to the default (`tiberio_users.db`). See the **Common --db option** section below for the full resolution order and how to share one database with the server.

### add — create a new user

```bash
tiberio-users add USERNAME [--db PATH] [--password PASSWORD]
```

```bash
# Interactive (prompted for password with confirmation)
uv run tiberio-users add alice

# Non-interactive (for scripts)
uv run tiberio-users add alice --password "s3cr3t"

# Use a specific database file
uv run tiberio-users add alice --db /var/lib/tiberio/users.db
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
tiberio-users list [--db PATH]
```

```bash
uv run tiberio-users list
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
tiberio-users delete USERNAME [--db PATH] [--yes]
```

```bash
# With confirmation prompt (default)
uv run tiberio-users delete alice

# Skip confirmation (useful in scripts)
uv run tiberio-users delete alice --yes
uv run tiberio-users delete alice -y
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
tiberio-users passwd USERNAME [--db PATH] [--password NEW_PASSWORD]
```

```bash
# Interactive (prompted)
uv run tiberio-users passwd alice

# Non-interactive
uv run tiberio-users passwd alice --password "newS3cr3t"
uv run tiberio-users passwd alice -p "newS3cr3t"
```

Updates the bcrypt hash for the user. Does **not** revoke existing tokens — active sessions remain valid until their JWTs expire.

- Exits with code `1` if the user does not exist.

---

## tiberio-beacon — publish the endpoint beacon

The AWS edge resolves the home server's address from `endpoint.json` in the S3
beacon bucket. `tiberio-beacon publish` writes that object with the current
public base URL. The server also publishes it automatically at startup and on
an interval (when `TIBERIO_BEACON_ENABLED=true`, every
`TIBERIO_BEACON_UPDATE_INTERVAL_SECONDS` seconds — default `300`); use the CLI
to publish on demand — for example from a tunnel hook when the URL rotates.

```
tiberio-beacon publish [--base-url URL] [--bucket NAME] [--key KEY] [--region REGION]
```

```bash
# Explicit URL
uv run tiberio-beacon publish --base-url https://your-tunnel.example.com

# Fall back to TIBERIO_PUBLIC_BASE_URL and the configured bucket/key/region
uv run tiberio-beacon publish
```

Each option defaults to the corresponding setting (`TIBERIO_PUBLIC_BASE_URL`,
`TIBERIO_S3_BEACON_BUCKET`, `TIBERIO_S3_BEACON_KEY`, `TIBERIO_AWS_REGION`).

- Exits with code `1` if no base URL is given (neither `--base-url` nor
  `TIBERIO_PUBLIC_BASE_URL`) or if the S3 write fails.

---

## tiberio-setup — deploy the AWS edge + Alexa account linking

`tiberio-setup` is a Typer app that automates the two halves of bringing the
skill online:

- **Infrastructure** — generate the home-server secrets, then drive the
  Terraform two-phase deploy (`terraform/deploy-aws.sh`: bootstrap + migrate).
- **Account linking** — render the `skill-package` templates from the Terraform
  outputs and push the manifest + account-linking config to the Alexa skill via
  the ASK CLI (`ask smapi`).

The final "enable + log in" step in the Alexa app is always manual; `run` prints
the remaining console steps when it finishes.

```bash
uv run tiberio-setup --help
```

| Subcommand | Purpose |
| --- | --- |
| `check` | Verify required external tooling (`terraform`, `aws`, `uv`; optional `ask`, `jq`) is installed |
| `secrets` | Ensure `.env` holds strong `TIBERIO_JWT_SECRET` / `TIBERIO_SHARED_SECRET` (generates the missing ones) |
| `infra` | Deploy the AWS edge via `terraform/deploy-aws.sh` (bootstrap + migrate) |
| `render` | Render `skill-package/build/*` from the Terraform deployment outputs |
| `link` | Push the rendered manifest + account linking to the skill (ASK CLI smapi) |
| `run` | Run the whole flow end to end |

### secrets — generate the home-server secrets

```bash
uv run tiberio-setup secrets [--env-file PATH] [--template PATH] [--force]
```

Creates `.env` from the template if missing, then fills any absent or too-short
secret in `TIBERIO_JWT_SECRET` and `TIBERIO_SHARED_SECRET` with a fresh 64-hex
value. Pass `--force` to regenerate even when secrets already exist.

### infra — deploy the AWS edge

```bash
uv run tiberio-setup infra --skill-id amzn1.ask.skill.… [--tfvars PATH] \
  [--tf-dir DIR] [--env-file PATH] [--skip-bootstrap] [--yes]
```

Runs the Terraform bootstrap (state bucket) and migrate phases. The
`TIBERIO_SHARED_SECRET` from `.env` is passed to Terraform via `TF_VAR_shared_secret`
so it never lands on the command line. Use `--skip-bootstrap` once the state
bucket already exists, and `--yes`/`-y` to auto-confirm the migrate apply.

### render — fill the skill-package templates

```bash
uv run tiberio-setup render [--tf-dir DIR] [--skill-package DIR] [--out-dir DIR] \
  [--directive-lambda-arn ARN] [--authorize-url URL] [--token-url URL]
```

Reads the Terraform `deployment_summary` output and writes
`skill-package/build/skill.json` and `accountLinking.json`. The Smart-Home
endpoint URI is filled from `directive_lambda_arn`, and the account-linking
`authorizationUrl` / `accessTokenUrl` from `oauth_authorize_url` /
`oauth_token_url`. Each value can be overridden with the matching flag (handy
when you have not deployed yet). Any remaining `REPLACE_WITH_` placeholders
(e.g. skill icons) are reported so you can fill them before publishing.

### link — push manifest + account linking to the skill

```bash
uv run tiberio-setup link --skill-id amzn1.ask.skill.… [--skill-package DIR] \
  [--out-dir DIR] [--stage development] [--profile NAME] [--allow-placeholders]
```

Requires the ASK CLI (`ask`) to be installed and configured (`ask configure`
writes `~/.ask/cli_config`). Calls `ask smapi update-skill-manifest` and
`update-account-linking-info` with the rendered files. It refuses to publish
while placeholders remain unless you pass `--allow-placeholders`, then prints
the remaining manual Alexa Developer Console steps.

### run — the whole flow end to end

```bash
uv run tiberio-setup run --skill-id amzn1.ask.skill.… [--tfvars PATH] \
  [--username NAME] [--base-url URL] [--stage development] [--profile NAME] \
  [--skip-infra] [--skip-link] [--allow-placeholders] [--yes]
```

Runs preflight → `secrets` → `infra` → `render` → `link` in order, skipping the
Terraform bootstrap automatically when state storage already exists. Optionally
creates a home-server user (`--username`, via `tiberio-users add`) and publishes
the beacon (`--base-url`, via `tiberio-beacon publish`). Use `--skip-infra` to
reuse existing infrastructure or `--skip-link` to render only.

::: tip The last step is manual
After `run`, three steps remain in the Alexa Developer Console / app: copy the
3 Alexa Redirect URLs into `TIBERIO_OAUTH_ALLOWED_REDIRECT_URIS` and restart the
server, make sure the tunnel is up and the beacon is published, then enable the
skill, log in, and run device discovery.
:::

---

## Common --db option

All `tiberio-users` subcommands resolve the database path in this order:

1. `--db PATH` flag
2. `USERS_DB_PATH` environment variable (the CLI's own Typer `envvar`, **unprefixed**)
3. `TIBERIO_USERS_DB_PATH` (the server setting, via `get_settings().users_db_path`)
4. Default: `tiberio_users.db` (in the current directory)

::: warning Two different env vars
The CLI's `--db` flag reads the **unprefixed** `USERS_DB_PATH`, while the **server** only reads the prefixed `TIBERIO_USERS_DB_PATH` (every setting uses the `TIBERIO_` prefix). To make sure the CLI and the server agree on one database, set **both** — or pass `--db` explicitly:

```bash
export TIBERIO_USERS_DB_PATH=/var/lib/tiberio/users.db   # used by the server
export USERS_DB_PATH=/var/lib/tiberio/users.db           # used by the CLI
uv run tiberio-users list
uv run tiberio-users add alice
```

:::

---

## Quick-start example

First-time setup from scratch:

```bash
# 1. Create a .env file with required secrets (note the TIBERIO_ prefix —
#    the server refuses to start without a strong TIBERIO_JWT_SECRET)
echo 'TIBERIO_JWT_SECRET=your-long-secret-at-least-32-chars' >> .env
echo 'TIBERIO_USERS_DB_PATH=tiberio_users.db' >> .env   # used by the server
echo 'USERS_DB_PATH=tiberio_users.db' >> .env           # used by tiberio-users

# 2. Create the first user (the server must NOT be running yet;
#    the CLI opens its own database connection)
uv run tiberio-users add alice

# 3. Start the server (creates the DB and tables if not present)
uv run tiberio

# 4. Verify
curl http://localhost:8080/health
```

::: tip Generate strong secrets automatically
`tiberio-setup secrets` writes a fresh `TIBERIO_JWT_SECRET` and
`TIBERIO_SHARED_SECRET` into `.env` for you — see
[tiberio-setup](#tiberio-setup-deploy-the-aws-edge-alexa-account-linking) below.
:::

::: tip Database on first run
`SqliteUserStore` creates both tables (`users`, `refresh_tokens`) automatically when `start()` is called — either by the server lifespan or by the CLI for each command. You never need to run migrations manually.
:::
