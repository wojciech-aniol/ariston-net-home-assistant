"""Tests for the Ariston NET binary sensors of a GALEVO device."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import ATTR_HOLIDAY

HOLIDAY = "binary_sensor.nimbus_ariston_net_holiday_mode"
FLAME = "binary_sensor.nimbus_ariston_net_is_flame_on"
HEATING_PUMP = "binary_sensor.nimbus_ariston_net_is_heating_pump_on"


def set_item(properties: dict[str, Any], item_id: str, **values: Any) -> None:
    """Change one item the fake cloud sends."""
    item = next(item for item in properties["items"] if item["id"] == item_id)
    item.update(values)


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("value", "expires_on", "expected_state"),
    [
        (True, "2026-11-01T00:00:00", STATE_ON),
        (False, None, STATE_OFF),
    ],
    ids=["on", "off"],
)
async def test_holiday_shows_end_date(
    hass: HomeAssistant,
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    value: bool,
    expires_on: str | None,
    expected_state: str,
) -> None:
    """Test the holiday sensor has the end date only while it is set."""
    set_item(properties, "Holiday", value=value, expiresOn=expires_on)

    await setup_integration(hass, config_entry)

    state = hass.states.get(HOLIDAY)
    assert state.state == expected_state
    assert state.attributes.get(ATTR_HOLIDAY) == expires_on


@pytest.mark.parametrize(
    ("entity_id", "item_id"),
    [(FLAME, "IsFlameOn"), (HEATING_PUMP, "IsHeatingPumpOn")],
)
@pytest.mark.parametrize(
    ("value", "expected_state"), [(True, STATE_ON), (False, STATE_OFF)]
)
async def test_binary_sensor_follows_device(
    hass: HomeAssistant,
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    entity_id: str,
    item_id: str,
    value: bool,
    expected_state: str,
) -> None:
    """Test the flame and heating pump sensors show the device value."""
    set_item(properties, item_id, value=value)

    await setup_integration(hass, config_entry)

    assert hass.states.get(entity_id).state == expected_state
