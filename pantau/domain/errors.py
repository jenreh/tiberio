"""Domain errors raised by use-cases and adapters."""

from __future__ import annotations


class DeviceNotFoundError(Exception):
    """Raised when an endpoint ID does not match any configured device."""

    def __init__(self, endpoint_id: str) -> None:
        super().__init__(f"Device not found: {endpoint_id!r}")
        self.endpoint_id = endpoint_id


class DeviceUnavailableError(Exception):
    """Raised when a device cannot be reached (network error, timeout, etc.).

    Maps to Alexa ENDPOINT_UNREACHABLE in the directive handler.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


class BeaconPublishError(Exception):
    """Raised when publishing the endpoint beacon to remote storage fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class DeviceCapabilityError(Exception):
    """Raised when a found device does not have the requested capability.

    Maps to Alexa INVALID_VALUE in the directive handler.
    """

    def __init__(self, endpoint_id: str, capability: str) -> None:
        super().__init__(
            f"Device {endpoint_id!r} does not support capability {capability!r}"
        )
        self.endpoint_id = endpoint_id
        self.capability = capability
