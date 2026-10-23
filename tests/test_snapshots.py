"""Snapshot tests of every Ariston NET entity."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.ariston_net import PLATFORMS


async def setup_platform(
    hass: HomeAssistant, entry: MockConfigEntry, platform: Platform
) -> None:
    """Set up the config entry with one platform only."""
    with patch("custom_components.ariston_net.PLATFORMS", [platform]):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.parametrize("platform", PLATFORMS)
async def test_default_data_entities_match_snapshot(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    platform: Platform,
) -> None:
    """Test the entities made from the default data stay the same."""
    await setup_platform(hass, config_entry, platform)

    await snapshot_platform(hass, entity_registry, snapshot, config_entry.entry_id)


@pytest.mark.parametrize("platform", PLATFORMS)
async def test_full_data_entities_match_snapshot(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    full_galevo: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    platform: Platform,
) -> None:
    """Test the entities made from the full GALEVO data stay the same."""
    await setup_platform(hass, config_entry, platform)

    await snapshot_platform(hass, entity_registry, snapshot, config_entry.entry_id)
