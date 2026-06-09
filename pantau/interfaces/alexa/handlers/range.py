"""Alexa.RangeController handler — SetRangeValue / AdjustRangeValue for blind endpoints.

Instance identifier: "Blind.Position" (per spec §5).
"""

from __future__ import annotations

import logging

from pantau.commands.blinds.adjust_blind_position import AdjustBlindPositionCommand
from pantau.commands.blinds.set_blind_position import SetBlindPositionCommand
from pantau.domain.errors import DeviceNotFoundError, DeviceUnavailableError
from pantau.interfaces.alexa.models import AlexaDirectiveRequest
from pantau.interfaces.alexa.response_builder import (
    build_error_response,
    build_property,
    build_response,
)

log = logging.getLogger(__name__)

BLIND_INSTANCE = "Blind.Position"


class RangeHandler:
    def __init__(
        self,
        set_blind_position: SetBlindPositionCommand,
        adjust_blind_position: AdjustBlindPositionCommand,
    ) -> None:
        self._set_blind_position = set_blind_position
        self._adjust_blind_position = adjust_blind_position

    async def handle(self, req: AlexaDirectiveRequest) -> dict:
        header = req.directive.header
        endpoint = req.directive.endpoint
        endpoint_id = endpoint.endpointId if endpoint else ""
        correlation_token = header.correlationToken
        bearer_token = endpoint.scope.token if endpoint and endpoint.scope else None

        try:
            if header.name == "SetRangeValue":
                range_value = int(req.directive.payload.get("rangeValue", 0))
                await self._set_blind_position.execute(endpoint_id, percent=range_value)
                result_value = range_value
            else:  # AdjustRangeValue
                delta = int(req.directive.payload.get("rangeValueDelta", 0))
                result_value = await self._adjust_blind_position.execute(
                    endpoint_id, delta=delta
                )

            properties = [
                build_property(
                    "Alexa.RangeController",
                    "rangeValue",
                    result_value,
                    instance=BLIND_INSTANCE,
                )
            ]
            return build_response(
                correlation_token, endpoint_id, bearer_token, properties
            )
        except ValueError as exc:
            return build_error_response(
                correlation_token, endpoint_id, "VALUE_OUT_OF_RANGE", str(exc)
            )
        except DeviceNotFoundError as exc:
            return build_error_response(
                correlation_token, endpoint_id, "NO_SUCH_ENDPOINT", str(exc)
            )
        except DeviceUnavailableError as exc:
            return build_error_response(
                correlation_token, endpoint_id, "ENDPOINT_UNREACHABLE", str(exc)
            )
        except Exception as exc:
            log.exception("RangeHandler: unexpected error for endpoint=%s", endpoint_id)
            return build_error_response(
                correlation_token, endpoint_id, "INTERNAL_ERROR", str(exc)
            )
