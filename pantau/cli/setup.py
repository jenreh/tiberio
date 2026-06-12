"""pantau-setup — one-shot setup orchestrator (KONZEPT §5/§6).

Automates the two halves of bringing the skill online:

  * Infrastructure: generates the home-server secrets, then drives the
    Terraform two-phase deploy (``terraform/deploy-aws.sh``).
  * Account linking: renders the ``skill-package`` templates from the
    Terraform outputs and pushes the manifest + account-linking config to the
    Alexa skill via the ASK CLI (``ask smapi``).

Commands:
  check      Verify required external tooling is installed.
  secrets    Ensure .env holds strong JWT/HMAC secrets (generates if missing).
  infra      Deploy the AWS edge via terraform/deploy-aws.sh (bootstrap + migrate).
  render     Render skill-package/build/* from the Terraform outputs.
  link       Push manifest + account linking to the skill (ASK CLI smapi).
  run        Run the whole flow end to end.

The final "enable + log in" step in the Alexa app is always manual; ``run``
prints the remaining console steps when it finishes.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import secrets as _secrets
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Any

import typer

log = logging.getLogger(__name__)

# pantau/cli/setup.py -> pantau/cli -> pantau -> project root
_PROJECT_ROOT = Path(__file__).parents[2]
DEFAULT_TF_DIR = _PROJECT_ROOT / "terraform"
DEFAULT_SKILL_PACKAGE = _PROJECT_ROOT / "skill-package"
DEFAULT_ENV_FILE = _PROJECT_ROOT / ".env"
DEFAULT_ENV_TEMPLATE = _PROJECT_ROOT / ".env.default"

SECRET_MIN_LEN = 32
REQUIRED_TOOLS = ("terraform", "aws", "uv")
OPTIONAL_TOOLS = ("ask", "jq")
SECRET_KEYS = ("PANTAU_JWT_SECRET", "PANTAU_SHARED_SECRET")
PLACEHOLDER_MARKER = "REPLACE_WITH_"

app = typer.Typer(
    name="pantau-setup",
    help="Initialise the AWS infrastructure and Alexa account linking.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# External seams (patched in tests)
# ---------------------------------------------------------------------------


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run an external command, streaming output unless ``capture_output``."""
    log.debug("Running command: %s", " ".join(args))
    return subprocess.run(  # noqa: S603 — args are built from trusted inputs
        args,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        input=input_text,
        text=True,
        check=check,
        capture_output=capture_output,
    )


def tool_available(name: str) -> bool:
    """Return True when ``name`` is on PATH."""
    return shutil.which(name) is not None


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def generate_secret() -> str:
    """Return a fresh 64-hex-char (32-byte) secret."""
    return _secrets.token_hex(SECRET_MIN_LEN)


def needs_secret(value: str | None, min_len: int = SECRET_MIN_LEN) -> bool:
    """True when ``value`` is missing or too short to be a real secret."""
    return value is None or len(value.strip()) < min_len


def parse_env(text: str) -> dict[str, str]:
    """Parse ``KEY=value`` lines, ignoring blanks and comments."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        result[key.strip()] = value.strip()
    return result


def upsert_env_lines(text: str, updates: dict[str, str]) -> str:
    """Replace existing ``KEY=`` lines and append the rest, preserving order."""
    lines = text.splitlines()
    remaining = dict(updates)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in remaining:
            lines[index] = f"{key}={remaining.pop(key)}"
    lines.extend(f"{key}={value}" for key, value in remaining.items())
    return "\n".join(lines) + "\n"


def render_skill_manifest(
    template: dict[str, Any], *, directive_lambda_arn: str
) -> dict[str, Any]:
    """Return the manifest envelope with every Smart-Home endpoint URI filled."""
    manifest = copy.deepcopy(template)
    smart_home = manifest["manifest"]["apis"]["smartHome"]
    smart_home["endpoint"]["uri"] = directive_lambda_arn
    for region in smart_home.get("regions", {}).values():
        region["endpoint"]["uri"] = directive_lambda_arn
    return manifest


def render_account_linking(
    template: dict[str, Any], *, authorize_url: str, token_url: str
) -> dict[str, Any]:
    """Return the *inner* AccountLinkingRequest object the ASK CLI expects.

    The skill-package template wraps the object under ``accountLinkingRequest``
    (the SMAPI REST envelope); the ``ask smapi update-account-linking-info
    --account-linking-request`` flag wants the bare object, so we unwrap.
    """
    inner = copy.deepcopy(template.get("accountLinkingRequest", template))
    inner["authorizationUrl"] = authorize_url
    inner["accessTokenUrl"] = token_url
    return inner


def find_placeholders(obj: Any) -> list[str]:
    """Collect every string still containing the REPLACE_WITH_ marker."""
    found: list[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for value in node:
                _walk(value)
        elif isinstance(node, str) and PLACEHOLDER_MARKER in node:
            found.append(node)

    _walk(obj)
    return found


def terraform_output(tf_dir: Path, name: str | None = None) -> Any:
    """Read a Terraform output as JSON (the whole output map when name=None)."""
    args = ["terraform", "output", "-json"]
    if name is not None:
        args.append(name)
    completed = run_command(args, cwd=tf_dir, capture_output=True)
    return json.loads(completed.stdout)


# ---------------------------------------------------------------------------
# Core logic (shared by the commands and the `run` orchestrator)
# ---------------------------------------------------------------------------


def _fail(message: str) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _preflight(*, require_ask: bool) -> None:
    missing = [tool for tool in REQUIRED_TOOLS if not tool_available(tool)]
    for tool in REQUIRED_TOOLS:
        typer.echo(f"{'✓' if tool not in missing else '✗'} {tool}")
    for tool in OPTIONAL_TOOLS:
        mark = "✓" if tool_available(tool) else "○"
        typer.echo(f"{mark} {tool} (optional)")
    if require_ask and not tool_available("ask"):
        missing.append("ask")
    if missing:
        _fail(f"missing required tool(s): {', '.join(missing)}")


def _ensure_secrets(env_file: Path, template: Path, *, force: bool) -> dict[str, str]:
    if not env_file.exists():
        seed = template.read_text() if template.exists() else ""
        env_file.write_text(seed)
        typer.echo(
            f"Created {env_file}" + (f" from {template}" if seed else " (empty)")
        )
    text = env_file.read_text()
    current = parse_env(text)
    updates = {
        key: generate_secret()
        for key in SECRET_KEYS
        if force or needs_secret(current.get(key))
    }
    if updates:
        env_file.write_text(upsert_env_lines(text, updates))
        for key in updates:
            typer.echo(f"Set {key} (generated)")
    else:
        typer.echo("Secrets already present; nothing to do.")
    return updates


def _resolve_outputs(
    tf_dir: Path,
    *,
    directive_lambda_arn: str | None,
    authorize_url: str | None,
    token_url: str | None,
) -> dict[str, str]:
    if directive_lambda_arn and authorize_url and token_url:
        return {
            "directive_lambda_arn": directive_lambda_arn,
            "oauth_authorize_url": authorize_url,
            "oauth_token_url": token_url,
        }
    summary = terraform_output(tf_dir, "deployment_summary")
    return {
        "directive_lambda_arn": directive_lambda_arn or summary["directive_lambda_arn"],
        "oauth_authorize_url": authorize_url or summary["oauth_authorize_url"],
        "oauth_token_url": token_url or summary["oauth_token_url"],
    }


def _render(skill_package: Path, out_dir: Path, outputs: dict[str, str]) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = render_skill_manifest(
        json.loads((skill_package / "skill.json").read_text()),
        directive_lambda_arn=outputs["directive_lambda_arn"],
    )
    linking = render_account_linking(
        json.loads((skill_package / "accountLinking.json").read_text()),
        authorize_url=outputs["oauth_authorize_url"],
        token_url=outputs["oauth_token_url"],
    )
    (out_dir / "skill.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    (out_dir / "accountLinking.json").write_text(
        json.dumps(linking, indent=2, ensure_ascii=False) + "\n"
    )
    typer.echo(f"Rendered skill.json + accountLinking.json -> {out_dir}")
    return find_placeholders(manifest) + find_placeholders(linking)


def _deploy_infra(
    tf_dir: Path,
    *,
    skill_id: str,
    tfvars: Path | None,
    env_file: Path,
    skip_bootstrap: bool,
    yes: bool,
) -> None:
    deploy = tf_dir / "deploy-aws.sh"
    if not deploy.exists():
        _fail(f"{deploy} not found")

    env = os.environ.copy()
    if env_file.exists():
        shared = parse_env(env_file.read_text()).get("PANTAU_SHARED_SECRET", "")
        if shared:
            # Pass the secret via TF_VAR_ env (not -var) so it never lands on
            # the command line / process table.
            env["TF_VAR_shared_secret"] = shared

    common: list[str] = []
    if tfvars is not None:
        common += ["--tfvars", str(tfvars)]
    common += ["-var", f"alexa_skill_id={skill_id}"]

    if not skip_bootstrap:
        run_command([str(deploy), "bootstrap", *common], cwd=tf_dir, env=env)
    run_command(
        [str(deploy), "migrate", *common],
        cwd=tf_dir,
        env=env,
        input_text="y\n" if yes else None,
    )
    typer.echo("Infrastructure deployed.")


def _link(
    skill_id: str,
    out_dir: Path,
    *,
    stage: str,
    profile: str | None,
    allow_placeholders: bool,
) -> None:
    if not tool_available("ask"):
        _fail("ASK CLI ('ask') not found — install it and run 'ask configure' first")

    manifest_file = out_dir / "skill.json"
    linking_file = out_dir / "accountLinking.json"
    for path in (manifest_file, linking_file):
        if not path.exists():
            _fail(f"{path} not found — run 'pantau-setup render' first")

    if not allow_placeholders:
        remaining = find_placeholders(
            json.loads(manifest_file.read_text())
        ) + find_placeholders(json.loads(linking_file.read_text()))
        if remaining:
            _fail(
                f"{len(remaining)} placeholder(s) remain in the rendered files "
                f"(e.g. {remaining[0]!r}); fill them or pass --allow-placeholders"
            )

    profile_args = ["--profile", profile] if profile else []
    run_command(
        [
            "ask",
            "smapi",
            "update-skill-manifest",
            "--skill-id",
            skill_id,
            "--stage",
            stage,
            "--manifest",
            f"file:{manifest_file}",
            *profile_args,
        ]
    )
    run_command(
        [
            "ask",
            "smapi",
            "update-account-linking-info",
            "--skill-id",
            skill_id,
            "--stage",
            stage,
            "--account-linking-request",
            f"file:{linking_file}",
            *profile_args,
        ]
    )
    typer.echo("Skill manifest + account linking updated.")


def _print_manual_steps() -> None:
    typer.echo("")
    typer.echo("Remaining manual steps (Alexa Developer Console / app):")
    typer.echo(
        "  1. Copy the 3 Alexa Redirect URLs from Account Linking into "
        "PANTAU_OAUTH_ALLOWED_REDIRECT_URIS (comma-separated) and restart the server."
    )
    typer.echo("  2. Ensure the tunnel is running and the beacon is published.")
    typer.echo(
        "  3. Alexa app -> skill -> Enable to use -> log in, then run device discovery."
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def check() -> None:
    """Verify required external tooling is installed."""
    _preflight(require_ask=False)


@app.command(name="secrets")
def ensure_secrets_cmd(
    env_file: Annotated[
        Path, typer.Option("--env-file", help="Target .env file.")
    ] = DEFAULT_ENV_FILE,
    template: Annotated[
        Path, typer.Option("--template", help="Template used to seed a missing .env.")
    ] = DEFAULT_ENV_TEMPLATE,
    force: Annotated[
        bool, typer.Option("--force", help="Regenerate even if secrets exist.")
    ] = False,
) -> None:
    """Ensure .env holds strong JWT/HMAC secrets (generates the missing ones)."""
    _ensure_secrets(env_file, template, force=force)


@app.command()
def render(
    tf_dir: Annotated[
        Path, typer.Option("--tf-dir", help="Terraform directory.")
    ] = DEFAULT_TF_DIR,
    skill_package: Annotated[
        Path, typer.Option("--skill-package", help="skill-package directory.")
    ] = DEFAULT_SKILL_PACKAGE,
    out_dir: Annotated[
        Path | None,
        typer.Option("--out-dir", help="Output dir (default skill-package/build)."),
    ] = None,
    directive_lambda_arn: Annotated[
        str | None,
        typer.Option("--directive-lambda-arn", help="Override Terraform output."),
    ] = None,
    authorize_url: Annotated[
        str | None, typer.Option("--authorize-url", help="Override Terraform output.")
    ] = None,
    token_url: Annotated[
        str | None, typer.Option("--token-url", help="Override Terraform output.")
    ] = None,
) -> None:
    """Render skill-package/build/* from the Terraform deployment outputs."""
    outputs = _resolve_outputs(
        tf_dir,
        directive_lambda_arn=directive_lambda_arn,
        authorize_url=authorize_url,
        token_url=token_url,
    )
    remaining = _render(skill_package, out_dir or (skill_package / "build"), outputs)
    if remaining:
        typer.echo(
            f"⚠ {len(remaining)} placeholder(s) remain (e.g. icons); "
            "fill them before publishing."
        )


@app.command()
def infra(
    skill_id: Annotated[
        str, typer.Option("--skill-id", help="Alexa skill ID (amzn1.ask.skill.…).")
    ],
    tfvars: Annotated[
        Path | None, typer.Option("--tfvars", help="Terraform variables file.")
    ] = None,
    tf_dir: Annotated[
        Path, typer.Option("--tf-dir", help="Terraform directory.")
    ] = DEFAULT_TF_DIR,
    env_file: Annotated[
        Path, typer.Option("--env-file", help=".env to read PANTAU_SHARED_SECRET from.")
    ] = DEFAULT_ENV_FILE,
    skip_bootstrap: Annotated[
        bool, typer.Option("--skip-bootstrap", help="Skip the state-bucket phase.")
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Auto-confirm the migrate apply.")
    ] = False,
) -> None:
    """Deploy the AWS edge via terraform/deploy-aws.sh (bootstrap + migrate)."""
    _deploy_infra(
        tf_dir,
        skill_id=skill_id,
        tfvars=tfvars,
        env_file=env_file,
        skip_bootstrap=skip_bootstrap,
        yes=yes,
    )


@app.command()
def link(
    skill_id: Annotated[
        str, typer.Option("--skill-id", help="Alexa skill ID (amzn1.ask.skill.…).")
    ],
    skill_package: Annotated[
        Path, typer.Option("--skill-package", help="skill-package directory.")
    ] = DEFAULT_SKILL_PACKAGE,
    out_dir: Annotated[
        Path | None,
        typer.Option("--out-dir", help="Rendered dir (default skill-package/build)."),
    ] = None,
    stage: Annotated[str, typer.Option("--stage", help="Skill stage.")] = "development",
    profile: Annotated[
        str | None, typer.Option("--profile", help="ASK CLI profile.")
    ] = None,
    allow_placeholders: Annotated[
        bool,
        typer.Option("--allow-placeholders", help="Push even if placeholders remain."),
    ] = False,
) -> None:
    """Push the rendered manifest + account linking to the skill (ASK CLI smapi)."""
    _link(
        skill_id,
        out_dir or (skill_package / "build"),
        stage=stage,
        profile=profile,
        allow_placeholders=allow_placeholders,
    )
    _print_manual_steps()


@app.command(name="run")
def run_all(
    skill_id: Annotated[
        str, typer.Option("--skill-id", help="Alexa skill ID (amzn1.ask.skill.…).")
    ],
    tfvars: Annotated[
        Path | None, typer.Option("--tfvars", help="Terraform variables file.")
    ] = None,
    username: Annotated[
        str | None, typer.Option("--username", help="Create this home-server user.")
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="Publish this tunnel URL to beacon."),
    ] = None,
    stage: Annotated[str, typer.Option("--stage", help="Skill stage.")] = "development",
    profile: Annotated[
        str | None, typer.Option("--profile", help="ASK CLI profile.")
    ] = None,
    tf_dir: Annotated[
        Path, typer.Option("--tf-dir", help="Terraform directory.")
    ] = DEFAULT_TF_DIR,
    skill_package: Annotated[
        Path, typer.Option("--skill-package", help="skill-package directory.")
    ] = DEFAULT_SKILL_PACKAGE,
    env_file: Annotated[
        Path, typer.Option("--env-file", help="Target .env file.")
    ] = DEFAULT_ENV_FILE,
    skip_infra: Annotated[
        bool, typer.Option("--skip-infra", help="Reuse existing infrastructure.")
    ] = False,
    skip_link: Annotated[
        bool, typer.Option("--skip-link", help="Render only, do not call ASK CLI.")
    ] = False,
    allow_placeholders: Annotated[
        bool, typer.Option("--allow-placeholders", help="Push despite placeholders.")
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Auto-confirm the migrate apply.")
    ] = False,
) -> None:
    """Run the whole flow: secrets -> infra -> render -> link (+ user/beacon)."""
    typer.echo("== Preflight ==")
    _preflight(require_ask=not skip_link)

    typer.echo("== Secrets ==")
    _ensure_secrets(env_file, DEFAULT_ENV_TEMPLATE, force=False)

    if not skip_infra:
        typer.echo("== Infrastructure ==")
        _deploy_infra(
            tf_dir,
            skill_id=skill_id,
            tfvars=tfvars,
            env_file=env_file,
            skip_bootstrap=False,
            yes=yes,
        )
    else:
        typer.echo("== Infrastructure (skipped) ==")

    typer.echo("== Render ==")
    outputs = _resolve_outputs(
        tf_dir, directive_lambda_arn=None, authorize_url=None, token_url=None
    )
    out_dir = skill_package / "build"
    remaining = _render(skill_package, out_dir, outputs)
    if remaining and not (skip_link or allow_placeholders):
        typer.echo(
            f"⚠ {len(remaining)} placeholder(s) remain (e.g. icons); fill them or "
            "re-run with --allow-placeholders before the manifest will publish."
        )

    if username:
        typer.echo("== User ==")
        run_command(["uv", "run", "pantau-users", "add", username])

    if base_url:
        typer.echo("== Beacon ==")
        run_command(["uv", "run", "pantau-beacon", "publish", "--base-url", base_url])

    if not skip_link:
        typer.echo("== Account linking ==")
        _link(
            skill_id,
            out_dir,
            stage=stage,
            profile=profile,
            allow_placeholders=allow_placeholders,
        )

    _print_manual_steps()


def main() -> None:  # pragma: no cover
    app()
