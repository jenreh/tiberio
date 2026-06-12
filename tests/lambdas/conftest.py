"""Fixtures for the AWS Lambda proxy tests.

The ``lambda`` directory cannot be a regular package (``lambda`` is a Python
keyword), so the handler modules are loaded by file path. The ``lambda``
directory itself is put on ``sys.path`` so the handlers can import
``shared.beacon`` exactly like in the deployed zip layout.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from botocore.exceptions import ClientError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAMBDA_DIR = _REPO_ROOT / "lambda"

if str(_LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(_LAMBDA_DIR))


def _load_module(name: str, path: Path) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeS3Client:
    """Minimal S3 stand-in supporting conditional GETs via IfNoneMatch."""

    def __init__(self, body: bytes, etag: str = '"etag-1"') -> None:
        self.body = body
        self.etag = etag
        self.calls: list[dict[str, Any]] = []
        self.error: ClientError | None = None

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if kwargs.get("IfNoneMatch") == self.etag:
            raise ClientError(
                {
                    "Error": {"Code": "304", "Message": "Not Modified"},
                    "ResponseMetadata": {"HTTPStatusCode": 304},
                },
                "GetObject",
            )
        return {"Body": io.BytesIO(self.body), "ETag": self.etag}


class FakeBoto3:
    """boto3 stand-in returning pre-built fake clients."""

    def __init__(self, **clients: Any) -> None:
        self._clients = clients

    def client(self, service_name: str) -> Any:
        return self._clients[service_name]


def make_s3_error() -> ClientError:
    return ClientError(
        {
            "Error": {"Code": "AccessDenied", "Message": "denied"},
            "ResponseMetadata": {"HTTPStatusCode": 403},
        },
        "GetObject",
    )


@pytest.fixture(scope="session")
def directive_module() -> ModuleType:
    return _load_module(
        "directive_proxy_handler", _LAMBDA_DIR / "directive_proxy" / "handler.py"
    )


@pytest.fixture(scope="session")
def oauth_module() -> ModuleType:
    return _load_module(
        "oauth_proxy_handler", _LAMBDA_DIR / "oauth_proxy" / "handler.py"
    )


@pytest.fixture
def directive_handler(directive_module: ModuleType) -> Any:
    directive_module.reset_warm_cache()
    yield directive_module
    directive_module.reset_warm_cache()


@pytest.fixture
def oauth_handler(oauth_module: ModuleType) -> Any:
    oauth_module.reset_warm_cache()
    yield oauth_module
    oauth_module.reset_warm_cache()


@pytest.fixture
def beacon_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PANTAU_BEACON_BUCKET", "pantau-alexa-beacon")
    monkeypatch.setenv("PANTAU_BEACON_KEY", "endpoint.json")
    monkeypatch.delenv("PANTAU_SHARED_SECRET", raising=False)
    monkeypatch.delenv("PANTAU_SHARED_SECRET_SSM_PARAM", raising=False)


@pytest.fixture
def fake_s3() -> FakeS3Client:
    body = (
        b'{"base_url": "https://home.example.net/", '
        b'"updated_at": "2026-06-11T00:00:00Z", "health": "ok"}'
    )
    return FakeS3Client(body)


@pytest.fixture
def patched_beacon_boto3(
    monkeypatch: pytest.MonkeyPatch, fake_s3: FakeS3Client
) -> FakeBoto3:
    import shared.beacon as beacon_module

    fake = FakeBoto3(s3=fake_s3)
    monkeypatch.setattr(beacon_module, "boto3", fake)
    return fake
