"""Contract tests for POST /alexa/directive.

Each test uses a verbatim-shaped directive from the official Alexa Smart Home API v3
docs and verifies the response matches the expected Alexa response format.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.interfaces.alexa.conftest import directive, discovery_directive


class TestPowerController:
    """Alexa.PowerController — TurnOn / TurnOff for channel endpoints."""

    def test_turn_on_zdf_returns_200(self, client: TestClient) -> None:
        resp = client.post(
            "/alexa/directive",
            json=directive("Alexa.PowerController", "TurnOn", endpoint_id="zdf"),
        )
        assert resp.status_code == 200

    def test_turn_on_returns_alexa_response_shape(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive("Alexa.PowerController", "TurnOn", endpoint_id="zdf"),
        ).json()

        event = body["event"]
        assert event["header"]["namespace"] == "Alexa"
        assert event["header"]["name"] == "Response"
        assert event["header"]["correlationToken"] == "test-correlation-token"
        assert event["header"]["payloadVersion"] == "3"
        assert event["endpoint"]["endpointId"] == "zdf"
        assert event["payload"] == {}

    def test_turn_on_reports_power_state_on(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive("Alexa.PowerController", "TurnOn", endpoint_id="zdf"),
        ).json()

        prop = body["context"]["properties"][0]
        assert prop["namespace"] == "Alexa.PowerController"
        assert prop["name"] == "powerState"
        assert prop["value"] == "ON"
        assert "timeOfSample" in prop
        assert prop["uncertaintyInMilliseconds"] == 500

    def test_turn_off_returns_power_state_off(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive("Alexa.PowerController", "TurnOff", endpoint_id="zdf"),
        ).json()

        prop = body["context"]["properties"][0]
        assert prop["namespace"] == "Alexa.PowerController"
        assert prop["value"] == "OFF"

    def test_unknown_endpoint_returns_error(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive("Alexa.PowerController", "TurnOn", endpoint_id="sky-sport"),
        ).json()

        event = body["event"]
        assert event["header"]["name"] == "ErrorResponse"
        assert event["payload"]["type"] == "NO_SUCH_ENDPOINT"


class TestSpeaker:
    """Alexa.Speaker — SetMute for the TV audio endpoint."""

    def test_set_mute_true_returns_200(self, client: TestClient) -> None:
        resp = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.Speaker",
                "SetMute",
                endpoint_id="tv-audio",
                payload={"mute": True},
            ),
        )
        assert resp.status_code == 200

    def test_set_mute_returns_alexa_response_shape(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.Speaker",
                "SetMute",
                endpoint_id="tv-audio",
                payload={"mute": True},
            ),
        ).json()

        event = body["event"]
        assert event["header"]["namespace"] == "Alexa"
        assert event["header"]["name"] == "Response"
        assert event["endpoint"]["endpointId"] == "tv-audio"

    def test_mute_true_reports_muted_property(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.Speaker",
                "SetMute",
                endpoint_id="tv-audio",
                payload={"mute": True},
            ),
        ).json()

        props = {p["name"]: p for p in body["context"]["properties"]}
        assert props["muted"]["namespace"] == "Alexa.Speaker"
        assert props["muted"]["value"] is True

    def test_mute_false_reports_unmuted(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.Speaker",
                "SetMute",
                endpoint_id="tv-audio",
                payload={"mute": False},
            ),
        ).json()

        props = {p["name"]: p for p in body["context"]["properties"]}
        assert props["muted"]["value"] is False

    def test_set_mute_unknown_endpoint_returns_error(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.Speaker", "SetMute", endpoint_id="bad-id", payload={"mute": True}
            ),
        ).json()

        assert body["event"]["payload"]["type"] == "NO_SUCH_ENDPOINT"

    def test_mute_state_preserved_across_calls(self, client: TestClient) -> None:
        """Assumed mute state persists across directives (singleton command)."""
        # First call: mute
        client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.Speaker",
                "SetMute",
                endpoint_id="tv-audio",
                payload={"mute": True},
            ),
        )
        # Second call: mute again — should still succeed (command is idempotent)
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.Speaker",
                "SetMute",
                endpoint_id="tv-audio",
                payload={"mute": True},
            ),
        ).json()
        props = {p["name"]: p for p in body["context"]["properties"]}
        assert props["muted"]["value"] is True


class TestThermostatController:
    """Alexa.ThermostatController — SetTargetTemperature."""

    def test_set_temperature_returns_200(self, client: TestClient) -> None:
        resp = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.ThermostatController",
                "SetTargetTemperature",
                endpoint_id="wohnzimmer-heizung",
                payload={"targetSetpoint": {"value": 22.0, "scale": "CELSIUS"}},
            ),
        )
        assert resp.status_code == 200

    def test_set_temperature_returns_alexa_response_shape(
        self, client: TestClient
    ) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.ThermostatController",
                "SetTargetTemperature",
                endpoint_id="wohnzimmer-heizung",
                payload={"targetSetpoint": {"value": 22.0, "scale": "CELSIUS"}},
            ),
        ).json()

        event = body["event"]
        assert event["header"]["namespace"] == "Alexa"
        assert event["header"]["name"] == "Response"
        assert event["endpoint"]["endpointId"] == "wohnzimmer-heizung"

    def test_set_temperature_reports_target_setpoint(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.ThermostatController",
                "SetTargetTemperature",
                endpoint_id="wohnzimmer-heizung",
                payload={"targetSetpoint": {"value": 22.0, "scale": "CELSIUS"}},
            ),
        ).json()

        prop = body["context"]["properties"][0]
        assert prop["namespace"] == "Alexa.ThermostatController"
        assert prop["name"] == "targetSetpoint"
        assert prop["value"]["value"] == 22.0
        assert prop["value"]["scale"] == "CELSIUS"

    def test_unknown_thermostat_returns_error(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.ThermostatController",
                "SetTargetTemperature",
                endpoint_id="bad-thermostat",
                payload={"targetSetpoint": {"value": 22.0, "scale": "CELSIUS"}},
            ),
        ).json()

        assert body["event"]["header"]["name"] == "ErrorResponse"
        assert body["event"]["payload"]["type"] == "NO_SUCH_ENDPOINT"

    def test_temperature_out_of_device_range_returns_value_out_of_range(
        self, client: TestClient
    ) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.ThermostatController",
                "SetTargetTemperature",
                endpoint_id="wohnzimmer-heizung",
                payload={"targetSetpoint": {"value": 26.0, "scale": "CELSIUS"}},
            ),
        ).json()

        assert body["event"]["header"]["name"] == "ErrorResponse"
        assert body["event"]["payload"]["type"] == "VALUE_OUT_OF_RANGE"


class TestRangeController:
    """Alexa.RangeController — SetRangeValue for blind endpoints."""

    def test_set_range_value_returns_200(self, client: TestClient) -> None:
        resp = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "SetRangeValue",
                endpoint_id="kueche-rollo",
                payload={"rangeValue": 50},
                instance="Blind.Position",
            ),
        )
        assert resp.status_code == 200

    def test_set_range_value_returns_alexa_response_shape(
        self, client: TestClient
    ) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "SetRangeValue",
                endpoint_id="kueche-rollo",
                payload={"rangeValue": 50},
                instance="Blind.Position",
            ),
        ).json()

        event = body["event"]
        assert event["header"]["namespace"] == "Alexa"
        assert event["header"]["name"] == "Response"
        assert event["endpoint"]["endpointId"] == "kueche-rollo"

    def test_set_range_value_reports_range_value_property(
        self, client: TestClient
    ) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "SetRangeValue",
                endpoint_id="kueche-rollo",
                payload={"rangeValue": 50},
                instance="Blind.Position",
            ),
        ).json()

        prop = body["context"]["properties"][0]
        assert prop["namespace"] == "Alexa.RangeController"
        assert prop["name"] == "rangeValue"
        assert prop["value"] == 50
        assert prop["instance"] == "Blind.Position"

    def test_unknown_blind_returns_error(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "SetRangeValue",
                endpoint_id="bad-blind",
                payload={"rangeValue": 50},
            ),
        ).json()

        assert body["event"]["payload"]["type"] == "NO_SUCH_ENDPOINT"


class TestDiscovery:
    """Alexa.Discovery — Discover returns all configured devices."""

    def test_discover_returns_200(self, client: TestClient) -> None:
        resp = client.post("/alexa/directive", json=discovery_directive())
        assert resp.status_code == 200

    def test_discover_returns_discovery_response_shape(
        self, client: TestClient
    ) -> None:
        body = client.post("/alexa/directive", json=discovery_directive()).json()

        event = body["event"]
        assert event["header"]["namespace"] == "Alexa.Discovery"
        assert event["header"]["name"] == "Discover.Response"
        assert event["header"]["payloadVersion"] == "3"
        assert "messageId" in event["header"]
        # No context, no correlationToken in discovery response
        assert "context" not in body
        assert "correlationToken" not in event["header"]

    def test_discover_returns_all_configured_devices(self, client: TestClient) -> None:
        body = client.post("/alexa/directive", json=discovery_directive()).json()
        endpoints = body["event"]["payload"]["endpoints"]

        # 2 channels + 1 audio + 1 blind + 1 thermostat = 5
        assert len(endpoints) == 5

    def test_discover_endpoint_ids_match_config(self, client: TestClient) -> None:
        body = client.post("/alexa/directive", json=discovery_directive()).json()
        ids = {e["endpointId"] for e in body["event"]["payload"]["endpoints"]}
        assert ids == {"zdf", "ard", "tv-audio", "kueche-rollo", "wohnzimmer-heizung"}

    def test_discover_channel_has_power_controller(self, client: TestClient) -> None:
        body = client.post("/alexa/directive", json=discovery_directive()).json()
        zdf = next(
            e for e in body["event"]["payload"]["endpoints"] if e["endpointId"] == "zdf"
        )
        interfaces = [c["interface"] for c in zdf["capabilities"]]
        assert "Alexa.PowerController" in interfaces
        assert "Alexa" in interfaces
        assert zdf["displayCategories"] == ["TV"]

    def test_discover_audio_has_speaker_capability(self, client: TestClient) -> None:
        body = client.post("/alexa/directive", json=discovery_directive()).json()
        audio = next(
            e
            for e in body["event"]["payload"]["endpoints"]
            if e["endpointId"] == "tv-audio"
        )
        interfaces = [c["interface"] for c in audio["capabilities"]]
        assert "Alexa.Speaker" in interfaces
        assert audio["displayCategories"] == ["SPEAKER"]

    def test_discover_thermostat_has_thermostat_controller(
        self, client: TestClient
    ) -> None:
        body = client.post("/alexa/directive", json=discovery_directive()).json()
        thermostat = next(
            e
            for e in body["event"]["payload"]["endpoints"]
            if e["endpointId"] == "wohnzimmer-heizung"
        )
        interfaces = [c["interface"] for c in thermostat["capabilities"]]
        assert "Alexa.ThermostatController" in interfaces
        assert thermostat["displayCategories"] == ["THERMOSTAT"]

    def test_discover_blind_has_range_controller_with_instance(
        self, client: TestClient
    ) -> None:
        body = client.post("/alexa/directive", json=discovery_directive()).json()
        blind = next(
            e
            for e in body["event"]["payload"]["endpoints"]
            if e["endpointId"] == "kueche-rollo"
        )
        range_cap = next(
            c
            for c in blind["capabilities"]
            if c.get("interface") == "Alexa.RangeController"
        )
        assert range_cap["instance"] == "Blind.Position"
        assert range_cap["configuration"]["supportedRange"]["maximumValue"] == 100
        assert "semantics" in range_cap
        assert blind["displayCategories"] == ["INTERIOR_BLIND"]


class TestDirectiveRouterEdgeCases:
    """Router-level error handling."""

    def test_unknown_namespace_returns_error(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive("Alexa.UnknownCapability", "DoSomething"),
        ).json()

        event = body["event"]
        assert event["header"]["name"] == "ErrorResponse"
        assert event["payload"]["type"] == "INVALID_DIRECTIVE"

    def test_malformed_body_returns_error(self, client: TestClient) -> None:
        # Body has token (passes mock validation) but directive structure is invalid
        body = client.post(
            "/alexa/directive",
            json={
                "directive": {
                    "header": {"namespace": "Alexa.PowerController", "name": "TurnOn"},
                    "endpoint": {
                        "scope": {"type": "BearerToken", "token": "test-bearer-token"},
                        "endpointId": "zdf",
                    },
                    # missing required fields: messageId, payloadVersion
                }
            },
        ).json()

        event = body["event"]
        assert event["header"]["name"] == "ErrorResponse"

    def test_body_with_no_token_returns_401(self, client: TestClient) -> None:
        resp = client.post("/alexa/directive", json={"not_a_directive": True})
        assert resp.status_code == 401

    def test_correlation_token_echoed_in_response(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.PowerController",
                "TurnOn",
                endpoint_id="zdf",
                correlation_token="my-unique-token-xyz",
            ),
        ).json()

        assert body["event"]["header"]["correlationToken"] == "my-unique-token-xyz"


class TestAdjustRangeValue:
    """Alexa.RangeController — AdjustRangeValue (Lower/Raise semantics)."""

    def test_adjust_range_value_returns_200(self, client: TestClient) -> None:
        resp = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "AdjustRangeValue",
                endpoint_id="kueche-rollo",
                payload={"rangeValueDelta": 10, "rangeValueDeltaDefault": False},
                instance="Blind.Position",
            ),
        )
        assert resp.status_code == 200

    def test_raise_blind_returns_higher_position(self, client: TestClient) -> None:
        # Set a known starting position first
        client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "SetRangeValue",
                endpoint_id="kueche-rollo",
                payload={"rangeValue": 50},
            ),
        )
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "AdjustRangeValue",
                endpoint_id="kueche-rollo",
                payload={"rangeValueDelta": 10, "rangeValueDeltaDefault": False},
                instance="Blind.Position",
            ),
        ).json()

        prop = body["context"]["properties"][0]
        assert prop["namespace"] == "Alexa.RangeController"
        assert prop["name"] == "rangeValue"
        assert prop["value"] == 60
        assert prop["instance"] == "Blind.Position"

    def test_lower_blind_returns_lower_position(self, client: TestClient) -> None:
        client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "SetRangeValue",
                endpoint_id="kueche-rollo",
                payload={"rangeValue": 50},
            ),
        )
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "AdjustRangeValue",
                endpoint_id="kueche-rollo",
                payload={"rangeValueDelta": -10, "rangeValueDeltaDefault": False},
                instance="Blind.Position",
            ),
        ).json()

        assert body["context"]["properties"][0]["value"] == 40

    def test_adjust_clamps_at_100(self, client: TestClient) -> None:
        client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "SetRangeValue",
                endpoint_id="kueche-rollo",
                payload={"rangeValue": 95},
            ),
        )
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "AdjustRangeValue",
                endpoint_id="kueche-rollo",
                payload={"rangeValueDelta": 10, "rangeValueDeltaDefault": False},
            ),
        ).json()

        assert body["context"]["properties"][0]["value"] == 100

    def test_adjust_clamps_at_0(self, client: TestClient) -> None:
        client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "SetRangeValue",
                endpoint_id="kueche-rollo",
                payload={"rangeValue": 5},
            ),
        )
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "AdjustRangeValue",
                endpoint_id="kueche-rollo",
                payload={"rangeValueDelta": -10, "rangeValueDeltaDefault": False},
            ),
        ).json()

        assert body["context"]["properties"][0]["value"] == 0

    def test_adjust_unknown_endpoint_returns_error(self, client: TestClient) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "AdjustRangeValue",
                endpoint_id="nein-gibt-es-nicht",
                payload={"rangeValueDelta": 10, "rangeValueDeltaDefault": False},
            ),
        ).json()

        assert body["event"]["payload"]["type"] == "NO_SUCH_ENDPOINT"


class TestHandlerValidation:
    """Payload validation and error-type correctness across handlers."""

    def test_range_out_of_bounds_returns_value_out_of_range(
        self, client: TestClient
    ) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.RangeController",
                "SetRangeValue",
                endpoint_id="kueche-rollo",
                payload={"rangeValue": 150},
            ),
        ).json()

        assert body["event"]["header"]["name"] == "ErrorResponse"
        assert body["event"]["payload"]["type"] == "VALUE_OUT_OF_RANGE"

    def test_thermostat_kelvin_scale_returns_value_out_of_range(
        self, client: TestClient
    ) -> None:
        body = client.post(
            "/alexa/directive",
            json=directive(
                "Alexa.ThermostatController",
                "SetTargetTemperature",
                endpoint_id="wohnzimmer-heizung",
                payload={"targetSetpoint": {"value": 293.15, "scale": "KELVIN"}},
            ),
        ).json()

        assert body["event"]["header"]["name"] == "ErrorResponse"
        assert body["event"]["payload"]["type"] == "VALUE_OUT_OF_RANGE"
