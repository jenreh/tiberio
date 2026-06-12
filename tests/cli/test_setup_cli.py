"""Tests for the pantau-setup CLI orchestrator."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import pantau.cli.setup as setup_cli

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _RecordingRunner:
    """Captures every run_command invocation and returns canned output."""

    def __init__(self, stdout_map: dict[str, str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._stdout_map = stdout_map or {}

    def __call__(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        input_text: str | None = None,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(
            {
                "args": args,
                "cwd": cwd,
                "env": env,
                "input_text": input_text,
                "capture_output": capture_output,
            }
        )
        stdout = ""
        for marker, value in self._stdout_map.items():
            if marker in args:
                stdout = value
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")


@pytest.fixture
def skill_package(tmp_path: Path) -> Path:
    """A minimal skill-package dir with placeholder templates."""
    pkg = tmp_path / "skill-package"
    pkg.mkdir()
    manifest = {
        "manifest": {
            "apis": {
                "smartHome": {
                    "endpoint": {"uri": "REPLACE_WITH_DIRECTIVE_LAMBDA_ARN"},
                    "regions": {
                        "EU": {"endpoint": {"uri": "REPLACE_WITH_DIRECTIVE_LAMBDA_ARN"}}
                    },
                }
            },
            "publishingInformation": {
                "locales": {"de-DE": {"smallIconUri": "REPLACE_WITH_SMALL_ICON_URI"}}
            },
        }
    }
    linking = {
        "accountLinkingRequest": {
            "type": "AUTH_CODE",
            "authorizationUrl": "REPLACE_WITH_OAUTH_AUTHORIZE_URL",
            "accessTokenUrl": "REPLACE_WITH_OAUTH_TOKEN_URL",
            "clientId": "alexa-skill",
        }
    }
    (pkg / "skill.json").write_text(json.dumps(manifest))
    (pkg / "accountLinking.json").write_text(json.dumps(linking))
    return pkg


_OUTPUTS = {
    "directive_lambda_arn": "arn:aws:lambda:eu-central-1:1:function:pantau-directive",
    "oauth_authorize_url": "https://api.example.com/oauth/authorize",
    "oauth_token_url": "https://api.example.com/oauth/token",
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestPureHelpers:
    def test_generate_secret_length(self) -> None:
        secret = setup_cli.generate_secret()
        assert len(secret) == setup_cli.SECRET_MIN_LEN * 2
        assert setup_cli.generate_secret() != secret

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(None, True), ("", True), ("short", True), ("x" * 32, False)],
    )
    def test_needs_secret(self, value: str | None, expected: bool) -> None:
        assert setup_cli.needs_secret(value) is expected

    def test_parse_env_ignores_comments_and_blanks(self) -> None:
        text = "# comment\n\nFOO=bar\nBAZ = qux \nnoequals\n"
        assert setup_cli.parse_env(text) == {"FOO": "bar", "BAZ": "qux"}

    def test_upsert_env_replaces_and_appends(self) -> None:
        text = "# header\nFOO=old\nKEEP=yes\n"
        result = setup_cli.upsert_env_lines(text, {"FOO": "new", "NEW": "added"})
        parsed = setup_cli.parse_env(result)
        assert parsed == {"FOO": "new", "KEEP": "yes", "NEW": "added"}
        assert result.startswith("# header")  # comments preserved

    def test_render_skill_manifest_fills_all_endpoints(self) -> None:
        template = {
            "manifest": {
                "apis": {
                    "smartHome": {
                        "endpoint": {"uri": "X"},
                        "regions": {"EU": {"endpoint": {"uri": "X"}}},
                    }
                }
            }
        }
        out = setup_cli.render_skill_manifest(template, directive_lambda_arn="arn:abc")
        smart = out["manifest"]["apis"]["smartHome"]
        assert smart["endpoint"]["uri"] == "arn:abc"
        assert smart["regions"]["EU"]["endpoint"]["uri"] == "arn:abc"
        assert template["manifest"]["apis"]["smartHome"]["endpoint"]["uri"] == "X"

    def test_render_account_linking_unwraps(self) -> None:
        template = {"accountLinkingRequest": {"type": "AUTH_CODE"}}
        out = setup_cli.render_account_linking(
            template, authorize_url="https://a", token_url="https://t"
        )
        assert "accountLinkingRequest" not in out
        assert out["authorizationUrl"] == "https://a"
        assert out["accessTokenUrl"] == "https://t"

    def test_find_placeholders(self) -> None:
        obj = {"a": "REPLACE_WITH_X", "b": ["ok", "REPLACE_WITH_Y"], "c": {"d": "ok"}}
        assert sorted(setup_cli.find_placeholders(obj)) == [
            "REPLACE_WITH_X",
            "REPLACE_WITH_Y",
        ]


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


class TestCheck:
    def test_all_tools_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(setup_cli, "tool_available", lambda _: True)
        result = runner.invoke(setup_cli.app, ["check"])
        assert result.exit_code == 0

    def test_missing_required_tool_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(setup_cli, "tool_available", lambda name: name != "aws")
        result = runner.invoke(setup_cli.app, ["check"])
        assert result.exit_code == 1
        assert "aws" in result.output


# ---------------------------------------------------------------------------
# secrets
# ---------------------------------------------------------------------------


class TestSecrets:
    def test_generates_missing_secrets(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("PANTAU_JWT_SECRET=\nPANTAU_SHARED_SECRET=\n")
        result = runner.invoke(setup_cli.app, ["secrets", "--env-file", str(env_file)])
        assert result.exit_code == 0
        parsed = setup_cli.parse_env(env_file.read_text())
        assert not setup_cli.needs_secret(parsed["PANTAU_JWT_SECRET"])
        assert not setup_cli.needs_secret(parsed["PANTAU_SHARED_SECRET"])

    def test_keeps_existing_strong_secrets(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        strong = "a" * 40
        env_file.write_text(
            f"PANTAU_JWT_SECRET={strong}\nPANTAU_SHARED_SECRET={strong}\n"
        )
        result = runner.invoke(setup_cli.app, ["secrets", "--env-file", str(env_file)])
        assert result.exit_code == 0
        assert "nothing to do" in result.output
        assert setup_cli.parse_env(env_file.read_text())["PANTAU_JWT_SECRET"] == strong

    def test_force_regenerates(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        strong = "a" * 40
        env_file.write_text(
            f"PANTAU_JWT_SECRET={strong}\nPANTAU_SHARED_SECRET={strong}\n"
        )
        result = runner.invoke(
            setup_cli.app, ["secrets", "--env-file", str(env_file), "--force"]
        )
        assert result.exit_code == 0
        assert setup_cli.parse_env(env_file.read_text())["PANTAU_JWT_SECRET"] != strong

    def test_seeds_from_template(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        template = tmp_path / ".env.default"
        template.write_text("PANTAU_PORT=8080\nPANTAU_JWT_SECRET=\n")
        result = runner.invoke(
            setup_cli.app,
            ["secrets", "--env-file", str(env_file), "--template", str(template)],
        )
        assert result.exit_code == 0
        parsed = setup_cli.parse_env(env_file.read_text())
        assert parsed["PANTAU_PORT"] == "8080"
        assert not setup_cli.needs_secret(parsed["PANTAU_JWT_SECRET"])


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


class TestRender:
    def test_render_with_explicit_outputs(self, skill_package: Path) -> None:
        out_dir = skill_package / "build"
        result = runner.invoke(
            setup_cli.app,
            [
                "render",
                "--skill-package",
                str(skill_package),
                "--out-dir",
                str(out_dir),
                "--directive-lambda-arn",
                _OUTPUTS["directive_lambda_arn"],
                "--authorize-url",
                _OUTPUTS["oauth_authorize_url"],
                "--token-url",
                _OUTPUTS["oauth_token_url"],
            ],
        )
        assert result.exit_code == 0
        manifest = json.loads((out_dir / "skill.json").read_text())
        smart = manifest["manifest"]["apis"]["smartHome"]
        assert smart["endpoint"]["uri"] == _OUTPUTS["directive_lambda_arn"]
        linking = json.loads((out_dir / "accountLinking.json").read_text())
        assert "accountLinkingRequest" not in linking
        assert linking["authorizationUrl"] == _OUTPUTS["oauth_authorize_url"]
        # icon placeholder still present -> warning
        assert "placeholder" in result.output.lower()

    def test_render_resolves_from_terraform(
        self, monkeypatch: pytest.MonkeyPatch, skill_package: Path
    ) -> None:
        recorder = _RecordingRunner({"deployment_summary": json.dumps(_OUTPUTS)})
        monkeypatch.setattr(setup_cli, "run_command", recorder)
        out_dir = skill_package / "build"
        result = runner.invoke(
            setup_cli.app,
            [
                "render",
                "--skill-package",
                str(skill_package),
                "--out-dir",
                str(out_dir),
                "--tf-dir",
                str(skill_package),
            ],
        )
        assert result.exit_code == 0
        assert any("deployment_summary" in c["args"] for c in recorder.calls)
        manifest = json.loads((out_dir / "skill.json").read_text())
        smart = manifest["manifest"]["apis"]["smartHome"]
        assert smart["endpoint"]["uri"] == _OUTPUTS["directive_lambda_arn"]


# ---------------------------------------------------------------------------
# infra
# ---------------------------------------------------------------------------


class TestInfra:
    def test_runs_bootstrap_and_migrate(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        tf_dir = tmp_path / "terraform"
        tf_dir.mkdir()
        (tf_dir / "deploy-aws.sh").write_text("#!/usr/bin/env zsh\n")
        env_file = tmp_path / ".env"
        env_file.write_text("PANTAU_SHARED_SECRET=" + "s" * 40 + "\n")
        recorder = _RecordingRunner()
        monkeypatch.setattr(setup_cli, "run_command", recorder)

        result = runner.invoke(
            setup_cli.app,
            [
                "infra",
                "--skill-id",
                "amzn1.ask.skill.abc",
                "--tf-dir",
                str(tf_dir),
                "--env-file",
                str(env_file),
                "--yes",
            ],
        )
        assert result.exit_code == 0
        commands = [c["args"][1] for c in recorder.calls]
        assert commands == ["bootstrap", "migrate"]
        # skill id passed as a -var, secret passed via TF_VAR env (never argv)
        assert "alexa_skill_id=amzn1.ask.skill.abc" in recorder.calls[0]["args"]
        assert recorder.calls[0]["env"]["TF_VAR_shared_secret"] == "s" * 40
        assert all(
            "TF_VAR_shared_secret" not in arg
            for c in recorder.calls
            for arg in c["args"]
        )
        assert recorder.calls[1]["input_text"] == "y\n"

    def test_skip_bootstrap(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        tf_dir = tmp_path / "terraform"
        tf_dir.mkdir()
        (tf_dir / "deploy-aws.sh").write_text("#!/usr/bin/env zsh\n")
        recorder = _RecordingRunner()
        monkeypatch.setattr(setup_cli, "run_command", recorder)
        result = runner.invoke(
            setup_cli.app,
            [
                "infra",
                "--skill-id",
                "amzn1.ask.skill.abc",
                "--tf-dir",
                str(tf_dir),
                "--env-file",
                str(tmp_path / "missing.env"),
                "--skip-bootstrap",
            ],
        )
        assert result.exit_code == 0
        assert [c["args"][1] for c in recorder.calls] == ["migrate"]

    def test_missing_deploy_script_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(setup_cli, "run_command", _RecordingRunner())
        result = runner.invoke(
            setup_cli.app,
            ["infra", "--skill-id", "x", "--tf-dir", str(tmp_path)],
        )
        assert result.exit_code == 1
        assert "deploy-aws.sh" in result.output


# ---------------------------------------------------------------------------
# link
# ---------------------------------------------------------------------------


class TestLink:
    def _render_build(self, skill_package: Path, *, with_icon: bool) -> Path:
        out_dir = skill_package / "build"
        out_dir.mkdir()
        manifest = {
            "manifest": {
                "apis": {"smartHome": {"endpoint": {"uri": "arn:abc"}}},
                "publishingInformation": {
                    "locales": {
                        "de-DE": {
                            "smallIconUri": "REPLACE_WITH_ICON"
                            if with_icon
                            else "https://x/i.png"
                        }
                    }
                },
            }
        }
        linking = {"type": "AUTH_CODE", "authorizationUrl": "https://a"}
        (out_dir / "skill.json").write_text(json.dumps(manifest))
        (out_dir / "accountLinking.json").write_text(json.dumps(linking))
        return out_dir

    def test_link_pushes_manifest_and_linking(
        self, monkeypatch: pytest.MonkeyPatch, skill_package: Path
    ) -> None:
        out_dir = self._render_build(skill_package, with_icon=False)
        monkeypatch.setattr(setup_cli, "tool_available", lambda _: True)
        recorder = _RecordingRunner()
        monkeypatch.setattr(setup_cli, "run_command", recorder)
        result = runner.invoke(
            setup_cli.app,
            ["link", "--skill-id", "amzn1.ask.skill.abc", "--out-dir", str(out_dir)],
        )
        assert result.exit_code == 0
        smapi_subcmds = [c["args"][2] for c in recorder.calls]
        assert smapi_subcmds == [
            "update-skill-manifest",
            "update-account-linking-info",
        ]
        manifest_call = recorder.calls[0]["args"]
        assert f"file:{out_dir / 'skill.json'}" in manifest_call
        assert "Redirect URL" in result.output

    def test_link_missing_ask_fails(
        self, monkeypatch: pytest.MonkeyPatch, skill_package: Path
    ) -> None:
        out_dir = self._render_build(skill_package, with_icon=False)
        monkeypatch.setattr(setup_cli, "tool_available", lambda _: False)
        result = runner.invoke(
            setup_cli.app,
            ["link", "--skill-id", "x", "--out-dir", str(out_dir)],
        )
        assert result.exit_code == 1
        assert "ask" in result.output.lower()

    def test_link_blocks_on_placeholders(
        self, monkeypatch: pytest.MonkeyPatch, skill_package: Path
    ) -> None:
        out_dir = self._render_build(skill_package, with_icon=True)
        monkeypatch.setattr(setup_cli, "tool_available", lambda _: True)
        recorder = _RecordingRunner()
        monkeypatch.setattr(setup_cli, "run_command", recorder)
        result = runner.invoke(
            setup_cli.app,
            ["link", "--skill-id", "x", "--out-dir", str(out_dir)],
        )
        assert result.exit_code == 1
        assert "placeholder" in result.output.lower()
        assert recorder.calls == []

    def test_link_allow_placeholders(
        self, monkeypatch: pytest.MonkeyPatch, skill_package: Path
    ) -> None:
        out_dir = self._render_build(skill_package, with_icon=True)
        monkeypatch.setattr(setup_cli, "tool_available", lambda _: True)
        recorder = _RecordingRunner()
        monkeypatch.setattr(setup_cli, "run_command", recorder)
        result = runner.invoke(
            setup_cli.app,
            [
                "link",
                "--skill-id",
                "x",
                "--out-dir",
                str(out_dir),
                "--allow-placeholders",
            ],
        )
        assert result.exit_code == 0
        assert len(recorder.calls) == 2

    def test_link_missing_render_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(setup_cli, "tool_available", lambda _: True)
        monkeypatch.setattr(setup_cli, "run_command", _RecordingRunner())
        result = runner.invoke(
            setup_cli.app,
            ["link", "--skill-id", "x", "--out-dir", str(tmp_path / "nope")],
        )
        assert result.exit_code == 1
        assert "render" in result.output.lower()


# ---------------------------------------------------------------------------
# run (orchestrator)
# ---------------------------------------------------------------------------


class TestRunAll:
    def test_full_flow(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, skill_package: Path
    ) -> None:
        tf_dir = tmp_path / "terraform"
        tf_dir.mkdir()
        (tf_dir / "deploy-aws.sh").write_text("#!/usr/bin/env zsh\n")
        env_file = tmp_path / ".env"
        # fill the icon so linking is not blocked
        manifest = json.loads((skill_package / "skill.json").read_text())
        manifest["manifest"]["publishingInformation"]["locales"]["de-DE"][
            "smallIconUri"
        ] = "https://x/i.png"
        (skill_package / "skill.json").write_text(json.dumps(manifest))

        monkeypatch.setattr(setup_cli, "tool_available", lambda _: True)
        recorder = _RecordingRunner({"deployment_summary": json.dumps(_OUTPUTS)})
        monkeypatch.setattr(setup_cli, "run_command", recorder)

        result = runner.invoke(
            setup_cli.app,
            [
                "run",
                "--skill-id",
                "amzn1.ask.skill.abc",
                "--tf-dir",
                str(tf_dir),
                "--skill-package",
                str(skill_package),
                "--env-file",
                str(env_file),
                "--username",
                "alice",
                "--base-url",
                "https://tunnel.example.com",
                "--yes",
            ],
        )
        assert result.exit_code == 0, result.output
        # secrets were written
        parsed = setup_cli.parse_env(env_file.read_text())
        assert not setup_cli.needs_secret(parsed["PANTAU_JWT_SECRET"])
        # the orchestrated external calls happened in order
        joined = [" ".join(c["args"]) for c in recorder.calls]
        assert any("bootstrap" in j for j in joined)
        assert any("migrate" in j for j in joined)
        assert any("pantau-users add alice" in j for j in joined)
        assert any("pantau-beacon publish" in j for j in joined)
        assert any("update-skill-manifest" in j for j in joined)
        assert any("update-account-linking-info" in j for j in joined)

    def test_skip_infra_and_link(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, skill_package: Path
    ) -> None:
        env_file = tmp_path / ".env"
        monkeypatch.setattr(setup_cli, "tool_available", lambda _: True)
        recorder = _RecordingRunner({"deployment_summary": json.dumps(_OUTPUTS)})
        monkeypatch.setattr(setup_cli, "run_command", recorder)
        result = runner.invoke(
            setup_cli.app,
            [
                "run",
                "--skill-id",
                "x",
                "--tf-dir",
                str(skill_package),
                "--skill-package",
                str(skill_package),
                "--env-file",
                str(env_file),
                "--skip-infra",
                "--skip-link",
            ],
        )
        assert result.exit_code == 0
        joined = [" ".join(c["args"]) for c in recorder.calls]
        assert not any("bootstrap" in j for j in joined)
        assert not any("update-skill-manifest" in j for j in joined)
