"""Tests for which entities Ariston NET creates."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

FLAME = "binary_sensor.nimbus_ariston_net_is_flame_on"
CH_RETURN_TEMP = "sensor.nimbus_ariston_net_ch_return_temp"


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(("has_flame", "expected"), [(True, True), (False, False)])
async def test_flame_sensor_needs_flame_value(
    hass: HomeAssistant,
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    has_flame: bool,
    expected: bool,
) -> None:
    """Test the flame sensor is skipped when the device has no flame value."""
    if not has_flame:
        properties["items"] = [
            item for item in properties["items"] if item["id"] != "IsFlameOn"
        ]

    await setup_integration(hass, config_entry)

    assert (hass.states.get(FLAME) is not None) is expected


@pytest.mark.parametrize(
    ("menu_items", "expected"),
    [([{"id": 124, "value": 31.5, "unit": "°C"}], True), ([], False)],
)
async def test_ch_return_temp_needs_menu_value(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    menu_items: list[dict[str, Any]],
    expected: bool,
) -> None:
    """Test the CH return temperature is skipped without a menu value."""
    api.async_get_menu_items.return_value = menu_items

    await setup_integration(hass, config_entry)

    state = hass.states.get(CH_RETURN_TEMP)
    assert (state is not None) is expected
    if expected:
        assert state.state == "31.5"
