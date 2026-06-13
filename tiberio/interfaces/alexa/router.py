"""Alexa directive router — maps (namespace, name) to capability handlers.

Adding support for a new capability requires only a new handler entry here
(Open/Closed Principle).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from tiberio.interfaces.alexa.handlers.discovery import DiscoveryHandler
from tiberio.interfaces.alexa.handlers.power import PowerHandler
from tiberio.interfaces.alexa.handlers.range import RangeHandler
from tiberio.interfaces.alexa.handlers.report_state import ReportStateHandler
from tiberio.interfaces.alexa.handlers.speaker import SpeakerHandler
from tiberio.interfaces.alexa.handlers.thermostat import ThermostatHandler
from tiberio.interfaces.alexa.models import AlexaDirectiveRequest
from tiberio.interfaces.alexa.response_builder import build_error_response

log = logging.getLogger(__name__)

HandlerFn = Callable[[AlexaDirectiveRequest], Awaitable[dict]]


class AlexaDirectiveRouter:
    """Routes an incoming Alexa directive to the correct capability handler."""

    def __init__(
        self,
        power: PowerHandler,
        speaker: SpeakerHandler,
        thermostat: ThermostatHandler,
        range_: RangeHandler,
        discovery: DiscoveryHandler,
        report_state: ReportStateHandler,
    ) -> None:
        self._dispatch: dict[tuple[str, str], HandlerFn] = {
            ("Alexa.PowerController", "TurnOn"): power.handle,
            ("Alexa.PowerController", "TurnOff"): power.handle,
            # Mute only — volume is deliberately unsupported (see SpeakerHandler).
            ("Alexa.Speaker", "SetMute"): speaker.handle,
            ("Alexa.ThermostatController", "SetTargetTemperature"): thermostat.handle,
            (
                "Alexa.ThermostatController",
                "AdjustTargetTemperature",
            ): thermostat.handle,
            ("Alexa.RangeController", "SetRangeValue"): range_.handle,
            ("Alexa.RangeController", "AdjustRangeValue"): range_.handle,
            ("Alexa.Discovery", "Discover"): discovery.handle,
            ("Alexa", "ReportState"): report_state.handle,
        }

    @property
    def directive_count(self) -> int:
        return len(self._dispatch)

    async def route(self, body: dict) -> dict:
        try:
            req = AlexaDirectiveRequest(**body)
        except Exception as exc:
            log.warning("AlexaDirectiveRouter: failed to parse directive: %s", exc)
            return build_error_response(None, None, "INVALID_DIRECTIVE", str(exc))

        key = (req.directive.header.namespace, req.directive.header.name)
        handler = self._dispatch.get(key)
        if handler is None:
            log.warning("AlexaDirectiveRouter: no handler for %s", key)
            correlation_token = req.directive.header.correlationToken
            endpoint_id = (
                req.directive.endpoint.endpointId if req.directive.endpoint else None
            )
            return build_error_response(
                correlation_token,
                endpoint_id,
                "INVALID_DIRECTIVE",
                f"Unsupported directive: {key[0]}.{key[1]}",
            )

        log.debug("AlexaDirectiveRouter: routing %s.%s", key[0], key[1])
        return await handler(req)
