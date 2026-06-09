"""Tests for TV commands: ActivateChannelCommand and SetTvMuteCommand."""

from __future__ import annotations

import pytest

from pantau.adapters.mock_tv_adapter import MockTvAdapter
from pantau.adapters.yaml_device_registry import YamlDeviceRegistry
from pantau.commands.tv.activate_channel import ActivateChannelCommand
from pantau.commands.tv.set_tv_mute import SetTvMuteCommand
from pantau.domain.errors import DeviceNotFoundError
from pantau.domain.values import MuteState


class TestActivateChannel:
    @pytest.fixture
    def adapter(self) -> MockTvAdapter:
        return MockTvAdapter()

    @pytest.fixture
    def command(
        self, registry: YamlDeviceRegistry, adapter: MockTvAdapter
    ) -> ActivateChannelCommand:
        return ActivateChannelCommand(registry, adapter)

    async def test_ensures_activity_and_sets_channel(
        self, command: ActivateChannelCommand, adapter: MockTvAdapter
    ) -> None:
        await command.execute("zdf")
        assert adapter.ensure_activity_calls == ["Fernseher"]
        assert adapter.set_channel_calls == ["2"]

    async def test_activates_ard_channel(
        self, command: ActivateChannelCommand, adapter: MockTvAdapter
    ) -> None:
        await command.execute("ard")
        assert adapter.ensure_activity_calls == ["Fernseher"]
        assert adapter.set_channel_calls == ["1"]

    async def test_always_calls_ensure_activity(
        self, command: ActivateChannelCommand, adapter: MockTvAdapter
    ) -> None:
        await command.execute("zdf")
        await command.execute("ard")
        assert adapter.ensure_activity_calls == ["Fernseher", "Fernseher"]
        assert adapter.set_channel_calls == ["2", "1"]

    async def test_unknown_endpoint_raises(
        self, command: ActivateChannelCommand
    ) -> None:
        with pytest.raises(DeviceNotFoundError):
            await command.execute("sky-sport")


class TestSetTvMute:
    @pytest.fixture
    def adapter(self) -> MockTvAdapter:
        return MockTvAdapter()

    @pytest.fixture
    def command(
        self, registry: YamlDeviceRegistry, adapter: MockTvAdapter
    ) -> SetTvMuteCommand:
        return SetTvMuteCommand(registry, adapter)

    async def test_mute_from_unmuted_sends_toggle(
        self, command: SetTvMuteCommand, adapter: MockTvAdapter
    ) -> None:
        await command.execute("tv-audio", mute=True)
        assert adapter.toggle_mute_count == 1
        assert command.assumed_state == MuteState.MUTED

    async def test_unmute_from_muted_sends_toggle(
        self, command: SetTvMuteCommand, adapter: MockTvAdapter
    ) -> None:
        await command.execute("tv-audio", mute=True)
        await command.execute("tv-audio", mute=False)
        assert adapter.toggle_mute_count == 2
        assert command.assumed_state == MuteState.UNMUTED

    async def test_mute_when_already_muted_skips_toggle(
        self, command: SetTvMuteCommand, adapter: MockTvAdapter
    ) -> None:
        await command.execute("tv-audio", mute=True)
        await command.execute("tv-audio", mute=True)
        assert adapter.toggle_mute_count == 1

    async def test_unmute_when_already_unmuted_skips_toggle(
        self, command: SetTvMuteCommand, adapter: MockTvAdapter
    ) -> None:
        await command.execute("tv-audio", mute=False)
        assert adapter.toggle_mute_count == 0

    async def test_initial_state_is_unmuted(self, command: SetTvMuteCommand) -> None:
        assert command.assumed_state == MuteState.UNMUTED

    async def test_unknown_endpoint_raises(self, command: SetTvMuteCommand) -> None:
        with pytest.raises(DeviceNotFoundError):
            await command.execute("bad-endpoint", mute=True)
