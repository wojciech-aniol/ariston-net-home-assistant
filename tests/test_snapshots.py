"""Snapshot tests of the entities and the device of a one-zone GALEVO device.

Other device types and more zones are not covered yet.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.ariston_net import PLATFORMS

from .conftest import refresh_energy

DATA_SETS = ["default", "full"]


async def setup_data_set(
    hass: HomeAssistant,
    request: pytest.FixtureRequest,
    entry: MockConfigEntry,
    data_set: str,
    platforms: list[Platform],
) -> None:
    """Set up the entry with one data set and only the given platforms."""
    if data_set == "full":
        request.getfixturevalue("full_galevo")
    with patch("custom_components.ariston_net.PLATFORMS", platforms):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    if data_set == "full":
        await refresh_energy(hass, request.getfixturevalue("api"))


@pytest.mark.parametrize("platform", PLATFORMS)
@pytest.mark.parametrize("data_set", DATA_SETS)
async def test_entities_match_snapshot(
    hass: HomeAssistant,
    request: pytest.FixtureRequest,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    freezer: FrozenDateTimeFactory,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    data_set: str,
    platform: Platform,
) -> None:
    """Test the entities of each data set stay the same."""
    freezer.move_to("2026-10-18 12:00:00+00:00")
    await setup_data_set(hass, request, config_entry, data_set, [platform])

    await snapshot_platform(hass, entity_registry, snapshot, config_entry.entry_id)


@pytest.mark.parametrize("data_set", DATA_SETS)
async def test_device_matches_snapshot(
    hass: HomeAssistant,
    request: pytest.FixtureRequest,
    device_registry: dr.DeviceRegistry,
    snapshot: SnapshotAssertion,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    data_set: str,
) -> None:
    """Test the device, with its identifiers, stays the same."""
    await setup_data_set(hass, request, config_entry, data_set, [Platform.SENSOR])

    devices = dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
    assert devices == snapshot
