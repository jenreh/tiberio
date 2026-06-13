"""Alexa.Speaker handler — SetMute only.

Volume control is intentionally NOT supported: the TV is driven by a toggle-only
IR remote, and exposing volume let Alexa send SetVolume/AdjustVolume (and the app
show a slider), which occasionally fired stray volume key presses during a mute
toggle. The skill must never change the volume, so only mute is handled here.
"""

from __future__ import annotations

import logging

from tiberio.commands.get_speaker_state import GetSpeakerStateCommand
from tiberio.commands.set_mute import SetMuteCommand
from tiberio.interfaces.alexa.handlers._base import (
    AlexaHandler,
    DirectiveContext,
    InvalidPayloadError,
    require_field,
)
from tiberio.interfaces.alexa.response_builder import build_property

log = logging.getLogger(__name__)


class SpeakerHandler(AlexaHandler):
    def __init__(
        self,
        set_mute: SetMuteCommand,
        get_speaker_state: GetSpeakerStateCommand,
    ) -> None:
        self._set_mute = set_mute
        self._get_speaker_state = get_speaker_state

    async def _execute(self, ctx: DirectiveContext) -> list[dict]:
        # Only SetMute is routed here; volume directives are not registered.
        mute = require_field(ctx.payload, "mute")
        if not isinstance(mute, bool):
            raise InvalidPayloadError("Payload field 'mute' must be a boolean")
        await self._set_mute.execute(ctx.endpoint_id, mute=mute)

        muted, _ = await self._get_speaker_state.execute(ctx.endpoint_id)
        return [build_property("Alexa.Speaker", "muted", muted)]
