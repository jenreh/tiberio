"""CapabilityResolverPort — commands depend on this, not on Container directly."""

from __future__ import annotations

from typing import Protocol, TypeVar

from pantau.domain.models import Device

T = TypeVar("T")


class CapabilityResolverPort(Protocol):
    def resolve(self, device: Device, capability: type[T]) -> T: ...

    def all_implementing(self, capability: type[T]) -> list[T]: ...
