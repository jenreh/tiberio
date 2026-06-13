"""Alexa.ReportState handler — returns the current state of an endpoint.

Alexa sends Alexa.ReportState to refresh the state it shows in the app and on
devices with a screen. The reply is an Alexa.StateReport carrying the same
context properties a directive response would report.
"""

from __future__ import annotations

import logging

from tiberio.commands.get_device_state import GetDeviceStateCommand
from tiberio.interfaces.alexa.handlers._base import AlexaHandler, DirectiveContext
from tiberio.interfaces.alexa.handlers.range import BLIND_INSTANCE
from tiberio.interfaces.alexa.response_builder import build_property, build_state_report

log = logging.getLogger(__name__)


class ReportStateHandler(AlexaHandler):
    def __init__(self, get_device_state: GetDeviceStateCommand) -> None:
        self._get_device_state = get_device_state

    async def _execute(self, ctx: DirectiveContext) -> list[dict]:
        state = await self._get_device_state.execute(ctx.endpoint_id)
        if state.capability == "temperature":
            properties = [
                build_property(
                    "Alexa.ThermostatController",
                    "targetSetpoint",
                    {"value": state.value, "scale": "CELSIUS"},
                ),
                build_property("Alexa.ThermostatController", "thermostatMode", "HEAT"),
            ]
            if state.current_celsius is not None:
                properties.append(
                    build_property(
                        "Alexa.TemperatureSensor",
                        "temperature",
                        {"value": state.current_celsius, "scale": "CELSIUS"},
                    )
                )
            # Reaching here means the FRITZ!Box answered, so the device is
            # reachable; without this the thermostat tile spins on "unknown
            # health" and never renders.
            properties.append(
                build_property("Alexa.EndpointHealth", "connectivity", {"value": "OK"})
            )
            return properties
        return [
            build_property(
                "Alexa.RangeController",
                "rangeValue",
                int(state.value),
                instance=BLIND_INSTANCE,
            )
        ]

    def _build_success(self, ctx: DirectiveContext, properties: list[dict]) -> dict:
        return build_state_report(
            ctx.correlation_token, ctx.endpoint_id, ctx.bearer_token, properties
        )
