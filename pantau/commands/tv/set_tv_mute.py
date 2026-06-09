"""Use-case: set the TV mute state (toggle-based, assumed-state tracking)."""

from __future__ import annotations

import logging

from pantau.domain.errors import DeviceNotFoundError
from pantau.domain.values import MuteState
from pantau.ports.device_registry_port import DeviceRegistryPort
from pantau.ports.tv_port import TvPort

log = logging.getLogger(__name__)


class SetTvMuteCommand:
    """Manages assumed mute state — must be wired as a singleton to survive across directives."""

    def __init__(self, registry: DeviceRegistryPort, tv: TvPort) -> None:
        self._registry = registry
        self._tv = tv
        self._assumed_state = MuteState.UNMUTED

    @property
    def assumed_state(self) -> MuteState:
        return self._assumed_state

    async def execute(self, endpoint_id: str, mute: bool) -> None:
        registry = self._registry.get_registry()
        if endpoint_id != registry.tv.audio.id:
            raise DeviceNotFoundError(endpoint_id)

        desired = MuteState.MUTED if mute else MuteState.UNMUTED
        if desired == self._assumed_state:
            log.info(
                "SetTvMute: endpoint=%s already in state=%s, skipping toggle",
                endpoint_id,
                desired.value,
            )
            return

        log.info(
            "SetTvMute: endpoint=%s toggle %s -> %s",
            endpoint_id,
            self._assumed_state.value,
            desired.value,
        )
        await self._tv.toggle_mute()
        self._assumed_state = desired
