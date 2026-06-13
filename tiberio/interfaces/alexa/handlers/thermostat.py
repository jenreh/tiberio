"""Alexa.ThermostatController handler — SetTargetTemperature / AdjustTargetTemperature."""

from __future__ import annotations

import logging
from typing import cast

from tiberio.commands.adjust_temperature import AdjustTemperatureCommand
from tiberio.commands.set_temperature import SetTemperatureCommand
from tiberio.interfaces.alexa.handlers._base import (
    AlexaHandler,
    DirectiveContext,
    InvalidPayloadError,
    require_field,
)
from tiberio.interfaces.alexa.response_builder import build_property

log = logging.getLogger(__name__)

_KELVIN_OFFSET = 273.15


def _to_celsius(value: float, scale: str) -> float:
    """Convert an absolute temperature to Celsius."""
    if scale == "CELSIUS":
        return value
    if scale == "FAHRENHEIT":
        return (value - 32) * 5 / 9
    if scale == "KELVIN":
        return value - _KELVIN_OFFSET
    raise ValueError(f"Unsupported temperature scale: {scale!r}")


def _delta_to_celsius(value: float, scale: str) -> float:
    """Convert a temperature *delta* to Celsius (factor only, no offset)."""
    if scale in ("CELSIUS", "KELVIN"):
        return value
    if scale == "FAHRENHEIT":
        return value * 5 / 9
    raise ValueError(f"Unsupported temperature scale: {scale!r}")


def _temperature_payload(payload: dict, field: str) -> tuple[float, str]:
    """Extract {value, scale} from a required temperature payload field."""
    raw = require_field(payload, field)
    if not isinstance(raw, dict):
        raise InvalidPayloadError(f"Payload field {field!r} must be an object")
    data = cast("dict[str, object]", raw)
    value = data.get("value")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidPayloadError(
            f"Payload field {field!r} must contain a numeric 'value'"
        )
    return float(value), str(data.get("scale", "CELSIUS"))


class ThermostatHandler(AlexaHandler):
    def __init__(
        self,
        set_temperature: SetTemperatureCommand,
        adjust_temperature: AdjustTemperatureCommand,
    ) -> None:
        self._set_temperature = set_temperature
        self._adjust_temperature = adjust_temperature

    async def _execute(self, ctx: DirectiveContext) -> list[dict]:
        if ctx.name == "AdjustTargetTemperature":
            value, scale = _temperature_payload(ctx.payload, "targetSetpointDelta")
            applied = await self._adjust_temperature.execute(
                ctx.endpoint_id, delta_celsius=_delta_to_celsius(value, scale)
            )
        else:  # SetTargetTemperature
            value, scale = _temperature_payload(ctx.payload, "targetSetpoint")
            applied = await self._set_temperature.execute(
                ctx.endpoint_id, celsius=_to_celsius(value, scale)
            )

        return [
            build_property(
                "Alexa.ThermostatController",
                "targetSetpoint",
                {"value": applied, "scale": "CELSIUS"},
            ),
            build_property("Alexa.ThermostatController", "thermostatMode", "HEAT"),
        ]
