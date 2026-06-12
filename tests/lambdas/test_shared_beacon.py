"""BeaconReader content validation and warm-container rotation.

The scheme check is security-relevant: it is the stated justification for
the ``# noqa: S310`` suppressions in both Lambda handlers, so it is pinned
here.
"""

from __future__ import annotations

import pytest
from shared.beacon import BeaconError, BeaconReader

from tests.lambdas.conftest import FakeS3Client


def _reader(body: bytes) -> BeaconReader:
    return BeaconReader(FakeS3Client(body), "pantau-alexa-beacon", "endpoint.json")


class TestBeaconContentValidation:
    def test_invalid_json_raises_beacon_error(self) -> None:
        with pytest.raises(BeaconError, match="not valid JSON"):
            _reader(b"{not json").get_base_url()

    def test_non_object_json_raises_beacon_error(self) -> None:
        with pytest.raises(BeaconError, match="not a JSON object"):
            _reader(b'["https://home.example.net"]').get_base_url()

    def test_missing_base_url_raises_beacon_error(self) -> None:
        with pytest.raises(BeaconError, match="base_url"):
            _reader(b'{"health": "ok"}').get_base_url()

    def test_empty_base_url_raises_beacon_error(self) -> None:
        with pytest.raises(BeaconError, match="base_url"):
            _reader(b'{"base_url": ""}').get_base_url()

    def test_non_string_base_url_raises_beacon_error(self) -> None:
        with pytest.raises(BeaconError, match="base_url"):
            _reader(b'{"base_url": 42}').get_base_url()

    def test_ftp_scheme_raises_beacon_error(self) -> None:
        with pytest.raises(BeaconError, match="https"):
            _reader(b'{"base_url": "ftp://home.example.net"}').get_base_url()

    def test_http_scheme_rejected_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PANTAU_ALLOW_INSECURE_BEACON", raising=False)
        with pytest.raises(BeaconError, match="https"):
            _reader(b'{"base_url": "http://home.example.net"}').get_base_url()

    def test_http_scheme_allowed_with_insecure_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PANTAU_ALLOW_INSECURE_BEACON", "true")
        reader = _reader(b'{"base_url": "http://home.example.net/"}')
        assert reader.get_base_url() == "http://home.example.net"

    def test_https_url_returned_without_trailing_slash(self) -> None:
        reader = _reader(b'{"base_url": "https://home.example.net/"}')
        assert reader.get_base_url() == "https://home.example.net"


class TestBeaconRotation:
    def test_new_etag_refreshes_cached_base_url(self) -> None:
        """The core rotation scenario: a warm container must pick up the
        new base_url as soon as the beacon object changes (new ETag)."""
        fake_s3 = FakeS3Client(
            b'{"base_url": "https://old.example.net"}', etag='"etag-1"'
        )
        reader = BeaconReader(fake_s3, "pantau-alexa-beacon", "endpoint.json")
        assert reader.get_base_url() == "https://old.example.net"

        fake_s3.body = b'{"base_url": "https://new.example.net"}'
        fake_s3.etag = '"etag-2"'

        assert reader.get_base_url() == "https://new.example.net"

    def test_unchanged_etag_serves_cached_base_url(self) -> None:
        fake_s3 = FakeS3Client(b'{"base_url": "https://home.example.net"}')
        reader = BeaconReader(fake_s3, "pantau-alexa-beacon", "endpoint.json")

        assert reader.get_base_url() == "https://home.example.net"
        assert reader.get_base_url() == "https://home.example.net"
        assert fake_s3.calls[1]["IfNoneMatch"] == fake_s3.etag
