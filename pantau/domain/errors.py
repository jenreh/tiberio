"""Domain errors raised by use-cases and adapters."""

from __future__ import annotations


class DeviceNotFoundError(Exception):
    """Raised when an endpoint ID does not match any configured device."""

    def __init__(self, endpoint_id: str) -> None:
        super().__init__(f"Device not found: {endpoint_id!r}")
        self.endpoint_id = endpoint_id
