"""Tests for the extra menu items (flow, return and evaporator temperatures)."""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from ariston_net_api.ariston_api import AristonAPI, ConnectionException
from ariston_net_api.const import ARISTON_API_URL
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.ariston_net.menu_items import add_extra_menu_items

from .conftest import GATEWAY, MENU_ITEMS, runtime_data, setup_integration

HP_WATER_FLOW_TEMP = "sensor.nimbus_heat_pump_flow_temperature"
CH_FLOW_MEASURED_TEMP = "sensor.nimbus_ch_flow_measured_temperature"
CH_FLOW_TEMP = "sensor.nimbus_ch_flow_temperature"
SIGNAL_STRENGTH = "sensor.nimbus_signal_strength"
SIGNAL_ITEM = {"id": 119, "value": 80.0, "unit": "%"}
HP_WATER_RETURN_TEMP = "sensor.nimbus_heat_pump_return_temperature"
HP_EVAPORATOR_TEMP = "sensor.nimbus_evaporator_temperature"
RETURN_ITEM = {"id": 342, "nodeId": "T_13.8.2", "value": 24.0, "unit": "°C"}
EVAPORATOR_ITEM = {"id": 347, "nodeId": "T_13.8.7", "value": -2.0, "unit": "°C"}


async def test_flow_sensors_show_menu_values(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    properties: dict[str, Any],
) -> None:
    """Test both flow sensors get their menu value and unit without ChFlowTemp."""
    properties["items"] = [i for i in properties["items"] if i["id"] != "ChFlowTemp"]
    api.menu_items_request.return_value = copy.deepcopy(MENU_ITEMS)

    await setup_integration(hass, config_entry)

    for entity_id, value in (
        (HP_WATER_FLOW_TEMP, "27.0"),
        (CH_FLOW_MEASURED_TEMP, "25.0"),
    ):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == value
        assert state.attributes["unit_of_measurement"] == "°C"


@pytest.mark.usefixtures("init_full_integration")
async def test_ch_flow_measured_temp_skipped_with_ch_flow_temp(
    hass: HomeAssistant,
) -> None:
    """Test the menu CH flow sensor is skipped when ChFlowTemp has a value."""
    assert hass.states.get(CH_FLOW_TEMP).state == "35.0"
    assert hass.states.get(CH_FLOW_MEASURED_TEMP) is None
    assert hass.states.get(HP_WATER_FLOW_TEMP).state == "27.0"


@pytest.mark.usefixtures("init_full_integration")
async def test_menu_items_come_in_one_request(api: MagicMock) -> None:
    """Test the extra items are asked for in the library's menu items request."""
    api.menu_items_request.assert_awaited_once()
    url = api.menu_items_request.await_args.args[0]
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
    api.menu_items_request.return_value = menu_items

    await setup_integration(hass, config_entry)

    assert hass.states.get(HP_WATER_FLOW_TEMP) is None
    assert hass.states.get(CH_FLOW_MEASURED_TEMP) is None


async def test_menu_items_without_answer_give_no_sensors(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test an empty cloud answer (HTTP 404) is the same as no menu items."""
    api.menu_items_request.return_value = None

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(HP_WATER_FLOW_TEMP) is None


async def poll(hass: HomeAssistant) -> None:
    """Run one state poll."""
    await runtime_data(hass).coordinator.async_refresh()


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
    api.menu_items_request.side_effect = ConnectionException(500)

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(SIGNAL_STRENGTH).state == "80.0"
    assert hass.states.get(HP_WATER_FLOW_TEMP) is None

    for _ in range(3):
        await poll(hass)

    assert api.menu_items_request.await_count == 3
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
    api.menu_items_request.side_effect = [
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

    assert api.menu_items_request.await_count == 7
    assert hass.states.get(HP_WATER_FLOW_TEMP).state == "27.0"


async def test_refusal_counts_only_when_library_items_work(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test a poll where both lists fail is not a refusal of the longer list."""
    down = ConnectionException(500)
    api.menu_items_request.side_effect = [copy.deepcopy(MENU_ITEMS), *[down] * 5]
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

    assert api.menu_items_request.await_count == 6


def relogin_error(status: int) -> ConnectionException:
    """Return the error of a failed new login: an empty one that wraps the status."""
    error = ConnectionException()
    error.__cause__ = ConnectionException(status)
    return error


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (ConnectionException("Invalid token"), ConfigEntryState.SETUP_ERROR),
        (
            ConnectionException("Login failed (password changed?)"),
            ConfigEntryState.SETUP_ERROR,
        ),
        (ConnectionException(), ConfigEntryState.SETUP_RETRY),
        (relogin_error(401), ConfigEntryState.SETUP_ERROR),
        (ConnectionException(429), ConfigEntryState.SETUP_RETRY),
    ],
    ids=["invalid-token", "login-failed", "no-status", "relogin-401", "429"],
)
async def test_auth_error_on_extra_items_is_raised(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    error: ConnectionException,
    state: ConfigEntryState,
) -> None:
    """Test an error without an HTTP status is not taken for a refused list."""
    library_get_menu_items = api.async_get_menu_items
    api.menu_items_request.side_effect = error

    await setup_integration(hass, config_entry)

    assert config_entry.state is state
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
    api.menu_items_request.side_effect = ConnectionException(429, "body")

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    library_get_menu_items.assert_not_awaited()


@pytest.mark.usefixtures("init_full_integration")
async def test_blocked_items_are_left_out_while_refused(api: MagicMock) -> None:
    """Test refused blocked IDs are asked once at setup and not polled."""
    api.blocked_menu_items_request.assert_awaited_once()
    url = api.blocked_menu_items_request.await_args.args[0]
    assert url.endswith(f"menuItems/{GATEWAY}?menuItems=342,343,344,345,346,347")
    assert api.menu_items_request.await_args.args[0].endswith(
        "menuItems=124,119,348,349"
    )


async def test_blocked_items_are_read_when_served(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test served return and evaporator items join the polled request and get sensors."""
    api.blocked_menu_items_request.side_effect = None
    api.blocked_menu_items_request.return_value = [
        RETURN_ITEM,
        {"id": 343, "nodeId": "T_13.8.3", "value": 1.0, "unit": ""},
        EVAPORATOR_ITEM,
    ]
    api.menu_items_request.return_value = [*MENU_ITEMS, RETURN_ITEM, EVAPORATOR_ITEM]

    await setup_integration(hass, config_entry)

    url = api.menu_items_request.await_args.args[0]
    assert url.endswith("menuItems=124,119,348,349,342,347")
    for entity_id, value in (
        (HP_WATER_RETURN_TEMP, "24.0"),
        (HP_EVAPORATOR_TEMP, "-2.0"),
    ):
        state = hass.states.get(entity_id)
        assert state.state == value
        assert state.attributes["unit_of_measurement"] == "°C"


@pytest.mark.parametrize(
    "answer",
    [
        [{**RETURN_ITEM, "nodeId": "T_13.8.9"}],
        [{**RETURN_ITEM, "value": None}],
        None,
    ],
    ids=["other-node", "no-value", "empty"],
)
async def test_blocked_items_need_their_node_and_value(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    answer: list[dict[str, Any]] | None,
) -> None:
    """Test a blocked ID joins the polled request only for its node with a value."""
    api.blocked_menu_items_request.side_effect = None
    api.blocked_menu_items_request.return_value = answer

    await setup_integration(hass, config_entry)

    assert api.menu_items_request.await_args.args[0].endswith(
        "menuItems=124,119,348,349"
    )
    assert hass.states.get(HP_WATER_RETURN_TEMP) is None


@pytest.mark.parametrize(
    "error",
    [
        ConnectionException(429, "body"),
        ConnectionException("Invalid token"),
        aiohttp.ClientError(),
        TimeoutError(),
    ],
    ids=["rate-limit", "invalid-token", "network", "timeout"],
)
async def test_blocked_items_error_does_not_stop_setup(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    error: Exception,
) -> None:
    """Test any error of the setup check leaves the blocked IDs out."""
    api.blocked_menu_items_request.side_effect = error

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert api.menu_items_request.await_args.args[0].endswith(
        "menuItems=124,119,348,349"
    )
