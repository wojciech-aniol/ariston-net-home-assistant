"""Tests for the extra menu items (HP water flow and CH flow temperature)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

from ariston.ariston_api import ConnectionException
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from .conftest import GATEWAY

HP_WATER_FLOW_TEMP = "sensor.nimbus_ariston_net_hp_water_flow_temp"
CH_FLOW_TEMP = "sensor.nimbus_ariston_net_ch_flow_temperature"
SIGNAL_STRENGTH = "sensor.nimbus_ariston_net_signal_strength"
SCAN_INTERVAL = timedelta(seconds=180)


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("init_full_integration")
async def test_flow_sensors_show_menu_values(hass: HomeAssistant) -> None:
    """Test both flow temperature sensors get their menu value and unit."""
    for entity_id, value in ((HP_WATER_FLOW_TEMP, "27.0"), (CH_FLOW_TEMP, "25.0")):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == value
        assert state.attributes["unit_of_measurement"] == "°C"


@pytest.mark.usefixtures("init_full_integration")
async def test_menu_items_come_in_one_request(api: MagicMock) -> None:
    """Test the extra items are asked for in the library's menu items request."""
    api._async_get.assert_awaited_once()
    url = api._async_get.await_args.args[0]
    assert f"menuItems/{GATEWAY}?menuItems=" in url
    assert url.endswith("menuItems=124,119,348,349")


@pytest.mark.parametrize(
    "menu_items",
    [
        [],
        [{"id": 348, "value": None, "unit": "°C"}],
        [{"id": 119, "value": 80.0, "unit": "%"}],
    ],
    ids=["empty", "no-value", "other-item"],
)
async def test_flow_sensors_need_their_menu_value(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    menu_items: list[dict[str, Any]],
) -> None:
    """Test the sensors are skipped when the cloud sends no value for them."""
    api._async_get.return_value = menu_items

    await setup_integration(hass, config_entry)

    assert hass.states.get(HP_WATER_FLOW_TEMP) is None
    assert hass.states.get(CH_FLOW_TEMP) is None


async def test_menu_items_without_answer_give_no_sensors(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test an empty cloud answer (HTTP 404) is the same as no menu items."""
    api._async_get.return_value = None

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(HP_WATER_FLOW_TEMP) is None


async def test_refused_extra_items_fall_back_to_library_items(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a refused longer list is dropped for good and the library list is used."""
    library_get_menu_items = api.async_get_menu_items
    library_get_menu_items.return_value = [{"id": 119, "value": 80.0, "unit": "%"}]
    api._async_get.side_effect = ConnectionException(500)

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(SIGNAL_STRENGTH).state == "80.0"
    assert hass.states.get(HP_WATER_FLOW_TEMP) is None

    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    api._async_get.assert_awaited_once()
    assert library_get_menu_items.await_count == 2


async def test_rate_limit_on_extra_items_backs_off(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test HTTP 429 is left to the coordinator and the library list is not used."""
    library_get_menu_items = api.async_get_menu_items
    api._async_get.side_effect = ConnectionException(429, "body")

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    library_get_menu_items.assert_not_awaited()
