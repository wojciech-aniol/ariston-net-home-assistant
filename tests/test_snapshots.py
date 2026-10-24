"""Snapshot tests of the entities and the device of each device type.

GALEVO has two data sets, with one zone. The other types have one with every
entity they can have, and BSB has two zones.
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

from .conftest import DEVICE_TYPES, GALEVO, refresh_energy, runtime_data

DATA_SETS = ["default", "full"]

# Platforms with entities for each device type other than GALEVO.
DEVICE_TYPE_PLATFORMS: dict[str, tuple[Platform, ...]] = {
    "bsb": (
        Platform.BINARY_SENSOR,
        Platform.CLIMATE,
        Platform.SENSOR,
        Platform.WATER_HEATER,
    ),
    "evo": (
        Platform.BINARY_SENSOR,
        Platform.NUMBER,
        Platform.SELECT,
        Platform.SENSOR,
        Platform.SWITCH,
    ),
    **dict.fromkeys(
        ["evo2", "andris2", "lux", "lux2"],
        (
            Platform.BINARY_SENSOR,
            Platform.NUMBER,
            Platform.SENSOR,
            Platform.SWITCH,
            Platform.WATER_HEATER,
        ),
    ),
}


async def setup_platforms(
    hass: HomeAssistant,
    request: pytest.FixtureRequest,
    entry: MockConfigEntry,
    platforms: list[Platform],
    data_set: str = "default",
) -> None:
    """Set up the entry with only the given platforms, and energy values if any."""
    if data_set == "full":
        request.getfixturevalue("full_galevo")
    with patch("custom_components.ariston_net.PLATFORMS", platforms):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    api: MagicMock = request.getfixturevalue("api")
    if (
        runtime_data(hass).energy_coordinator is not None
        and api.async_get_consumptions_sequences.return_value
    ):
        await refresh_energy(hass, api)


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
    await setup_platforms(hass, request, config_entry, [platform], data_set)

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
    await setup_platforms(hass, request, config_entry, [Platform.SENSOR], data_set)

    devices = dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
    assert devices == snapshot


def test_device_type_platforms_list_every_device_type() -> None:
    """Test each device type other than GALEVO has its platforms listed."""
    assert set(DEVICE_TYPE_PLATFORMS) == set(DEVICE_TYPES) - {GALEVO}


@pytest.mark.parametrize("device_type", DEVICE_TYPE_PLATFORMS)
async def test_device_type_has_entities_on_its_platforms(
    hass: HomeAssistant,
    request: pytest.FixtureRequest,
    entity_registry: er.EntityRegistry,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    device_type: str,
) -> None:
    """Test each device type has entities only on the platforms snapshotted below."""
    await setup_platforms(hass, request, config_entry, PLATFORMS)

    entries = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    assert {entry.domain for entry in entries} == set(
        DEVICE_TYPE_PLATFORMS[device_type]
    )


@pytest.mark.parametrize(
    ("device_type", "platform"),
    [
        (device_type, platform)
        for device_type, platforms in DEVICE_TYPE_PLATFORMS.items()
        for platform in platforms
    ],
)
async def test_device_type_entities_match_snapshot(
    hass: HomeAssistant,
    request: pytest.FixtureRequest,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    freezer: FrozenDateTimeFactory,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    platform: Platform,
) -> None:
    """Test the entities of each device type stay the same."""
    freezer.move_to("2026-10-18 12:00:00+00:00")
    await setup_platforms(hass, request, config_entry, [platform])

    await snapshot_platform(hass, entity_registry, snapshot, config_entry.entry_id)


@pytest.mark.parametrize("device_type", DEVICE_TYPE_PLATFORMS)
async def test_device_type_device_matches_snapshot(
    hass: HomeAssistant,
    request: pytest.FixtureRequest,
    device_registry: dr.DeviceRegistry,
    snapshot: SnapshotAssertion,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test the device of each device type, with its model, stays the same."""
    await setup_platforms(hass, request, config_entry, [Platform.SENSOR])

    devices = dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
    assert devices == snapshot
