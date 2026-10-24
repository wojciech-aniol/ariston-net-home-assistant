"""Tests for the extra menu items (HP water flow and CH flow temperature)."""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from ariston.ariston_api import AristonAPI, ConnectionException
from ariston.const import ARISTON_API_URL
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.ariston_net.const import COORDINATOR, DOMAIN
from custom_components.ariston_net.menu_items import add_extra_menu_items

from .conftest import GATEWAY, MENU_ITEMS

HP_WATER_FLOW_TEMP = "sensor.nimbus_ariston_net_hp_water_flow_temp"
CH_FLOW_TEMP = "sensor.nimbus_ariston_net_ch_flow_temperature"
SIGNAL_STRENGTH = "sensor.nimbus_ariston_net_signal_strength"
SIGNAL_ITEM = {"id": 119, "value": 80.0, "unit": "%"}


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


async def poll(hass: HomeAssistant) -> None:
    """Run one state poll."""
    await hass.data[DOMAIN][GATEWAY][COORDINATOR].async_refresh()


async def test_refusals_in_a_row_fall_back_to_library_items(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the longer list is dropped after three refusals in a row."""
    library_get_menu_items = api.async_get_menu_items
    library_get_menu_items.return_value = [SIGNAL_ITEM]
    api._async_get.side_effect = ConnectionException(500)

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(SIGNAL_STRENGTH).state == "80.0"
    assert hass.states.get(HP_WATER_FLOW_TEMP) is None

    for _ in range(3):
        await poll(hass)

    assert api._async_get.await_count == 3
    assert library_get_menu_items.await_count == 4
    assert "refused the extra menu items 3 times in a row" in caplog.text


async def test_refusal_between_answers_keeps_extra_items(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test a good answer resets the count of refusals."""
    refused = ConnectionException(500)
    api.async_get_menu_items.return_value = [SIGNAL_ITEM]
    api._async_get.side_effect = [
        copy.deepcopy(MENU_ITEMS),
        refused,
        refused,
        copy.deepcopy(MENU_ITEMS),
        refused,
        refused,
        copy.deepcopy(MENU_ITEMS),
    ]

    await setup_integration(hass, config_entry)
    for _ in range(6):
        await poll(hass)

    assert api._async_get.await_count == 7
    assert hass.states.get(HP_WATER_FLOW_TEMP).state == "27.0"


async def test_refusal_counts_only_when_library_items_work(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test a poll where both lists fail is not a refusal of the longer list."""
    down = ConnectionException(500)
    api._async_get.side_effect = [copy.deepcopy(MENU_ITEMS), *[down] * 5]
    api.async_get_menu_items.side_effect = [
        down,
        down,
        down,
        [SIGNAL_ITEM],
        [SIGNAL_ITEM],
    ]

    await setup_integration(hass, config_entry)
    for _ in range(5):
        await poll(hass)

    assert api._async_get.await_count == 6


@pytest.mark.parametrize(
    "error",
    [
        ConnectionException("Invalid token"),
        ConnectionException("Login failed (password changed?)"),
        ConnectionException(),
    ],
    ids=["invalid-token", "login-failed", "no-status"],
)
async def test_auth_error_on_extra_items_is_raised(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    error: ConnectionException,
) -> None:
    """Test an error without an HTTP status is not taken for a refused list."""
    library_get_menu_items = api.async_get_menu_items
    api._async_get.side_effect = error

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    library_get_menu_items.assert_not_awaited()


async def test_library_without_async_get_keeps_its_method(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a library without _async_get keeps its own menu items method."""
    del api._async_get
    api.async_get_menu_items.return_value = [SIGNAL_ITEM]

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(SIGNAL_STRENGTH).state == "80.0"
    assert hass.states.get(HP_WATER_FLOW_TEMP) is None
    assert "has no _async_get" in caplog.text


async def test_extra_items_url_extends_library_url() -> None:
    """Test the request URL is the library's URL plus the extra items."""
    api = AristonAPI("user", "password")
    with patch.object(AristonAPI, "_async_get", AsyncMock(return_value=[])) as get:
        await api.async_get_menu_items(GATEWAY)
        library_url = get.await_args.args[0]
        add_extra_menu_items(api, ARISTON_API_URL)
        await api.async_get_menu_items(GATEWAY)

    assert get.await_args.args[0] == f"{library_url},348,349"


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
