"""ListablePort — capability for adapters that can enumerate their backend devices."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

BackendStatus = Literal["ok", "unavailable"]


@dataclass
class BackendListResult:
    """Serialisable result from one backend's list_backend() call."""

    status: BackendStatus
    data: dict = field(default_factory=dict)
    error: str | None = None


@runtime_checkable
class ListablePort(Protocol):
    adapter_name: str

    async def list_backend(self) -> BackendListResult: ...
