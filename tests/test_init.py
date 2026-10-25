"""Tests for setting up Ariston NET."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import aiohttp
from ariston_net_api.ariston_api import ConnectionException
from ariston_net_api.const import (
    ARISTON_API_URL,
    ARISTON_USER_AGENT,
    ConsumptionTimeInterval,
    ConsumptionType,
)
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import (
    CONF_SCAN_INTERVAL,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import (
    API_URL_SETTING,
    API_USER_AGENT,
    BUS_ERRORS_SCAN_INTERVAL,
    DOMAIN,
    ENABLE_BUS_ERRORS,
    ENABLE_ENERGY,
    ENERGY_SCAN_INTERVAL,
)

from .conftest import runtime_data, setup_integration, tracebacks

CLIMATE = "climate.nimbus"
WATER_HEATER = "water_heater.nimbus"
HEATING_PUMP = "binary_sensor.nimbus_heat_pump"
PLANT_MODE = "select.nimbus_plant_mode"
DHW_CURRENT_TEMP = "sensor.nimbus_hot_water_temperature"
ERRORS_COUNT = "sensor.nimbus_bus_errors"
CH_ENERGY = "sensor.nimbus_heating_energy"

CH_ENERGY_SEQUENCE: dict[str, Any] = {
    "k": ConsumptionType.CENTRAL_HEATING_TOTAL_ENERGY.value,
    "p": ConsumptionTimeInterval.LAST_DAY.value,
    "v": [1.5, 2.5],
}


def error_logs(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Return error messages logged by the integration."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.ERROR
        and record.name.startswith("custom_components")
    ]


async def test_setup_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the entry loads and creates the main entities."""
    assert init_integration.state is ConfigEntryState.LOADED

    for entity_id in (
        CLIMATE,
        WATER_HEATER,
        HEATING_PUMP,
        PLANT_MODE,
        DHW_CURRENT_TEMP,
        ERRORS_COUNT,
    ):
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.state != STATE_UNAVAILABLE, entity_id

    assert hass.states.get(HEATING_PUMP).state == STATE_ON
    assert hass.states.get(DHW_CURRENT_TEMP).state == "47.5"
    assert error_logs(caplog) == []


@pytest.mark.parametrize(
    ("entry_data", "expected_url", "expected_user_agent"),
    [
        ({}, ARISTON_API_URL, ARISTON_USER_AGENT),
        (
            {
                API_URL_SETTING: "https://cloud.example.com/api/v2/",
                API_USER_AGENT: "TestAgent/1.0",
            },
            "https://cloud.example.com/api/v2/",
            "TestAgent/1.0",
        ),
    ],
    ids=["default", "custom"],
)
async def test_setup_connects_with_saved_api_settings(
    hass: HomeAssistant,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    entry_data: dict[str, str],
    expected_url: str,
    expected_user_agent: str,
) -> None:
    """Test setup logs in with the saved API URL and user agent."""
    hass.config_entries.async_update_entry(
        config_entry, data=config_entry.data | entry_data
    )

    await setup_integration(hass, config_entry)

    mock_ariston.async_connect.assert_awaited_once_with(
        "user@example.com", "test-password", expected_url, expected_user_agent
    )


@pytest.mark.parametrize(
    ("hp_sys", "hybrid_sys", "expected"),
    [(True, False, True), (False, False, False)],
)
async def test_heating_pump_sensor_follows_hp_sys(
    hass: HomeAssistant,
    features: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    hp_sys: bool,
    hybrid_sys: bool,
    expected: bool,
) -> None:
    """Test the heating pump sensor exists only on heat pump systems."""
    features["hpSys"] = hp_sys
    features["hybridSys"] = hybrid_sys

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert (hass.states.get(HEATING_PUMP) is not None) is expected


async def test_device_failure_retries_setup(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test setup is retried when the device state can't be read."""
    api.async_get_properties.side_effect = ConnectionException(500)

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert tracebacks(caplog) == []


async def test_energy_failure_does_not_fail_setup(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a failing energy refresh keeps the other entities."""
    api.async_get_consumptions_sequences.side_effect = ConnectionException(500)

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert not runtime_data(hass).energy_coordinator.last_update_success
    assert "Could not fetch Ariston energy data" in caplog.text
    assert hass.states.get(CLIMATE).state != STATE_UNAVAILABLE
    assert hass.states.get(PLANT_MODE).state == "Winter"


async def test_energy_sensors_created_with_energy_data(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test a total energy sensor waits for the energy data to change."""
    api.async_get_consumptions_sequences.return_value = [CH_ENERGY_SEQUENCE]

    await setup_integration(hass, config_entry)

    state = hass.states.get(CH_ENERGY)
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("last_reset") is None

    api.async_get_consumptions_sequences.return_value = [
        CH_ENERGY_SEQUENCE | {"v": [1.5, 2.5, 3.0]}
    ]
    await runtime_data(hass).energy_coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(CH_ENERGY)
    assert state.state == "3.0"
    assert state.attributes["last_reset"] is not None


async def test_energy_sensors_added_after_later_refresh(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test energy sensors appear once a later energy refresh works."""
    api.async_get_consumptions_sequences.side_effect = ConnectionException(500)
    await setup_integration(hass, config_entry)
    assert hass.states.get(CH_ENERGY) is None

    api.async_get_consumptions_sequences.side_effect = None
    api.async_get_consumptions_sequences.return_value = [CH_ENERGY_SEQUENCE]
    await runtime_data(hass).energy_coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(CH_ENERGY)
    assert state is not None
    assert state.state == STATE_UNKNOWN


async def test_bus_errors_failure_does_not_fail_setup(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a failing bus errors refresh keeps the other entities."""
    api.async_get_bus_errors.side_effect = ConnectionException(500)

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert not runtime_data(hass).bus_errors_coordinator.last_update_success
    assert "Could not fetch Ariston bus errors" in caplog.text
    assert hass.states.get(ERRORS_COUNT).state == STATE_UNAVAILABLE
    assert hass.states.get(CLIMATE).state != STATE_UNAVAILABLE
    assert hass.states.get(HEATING_PUMP).state == STATE_ON


async def test_energy_polling_can_be_disabled(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test the energy option skips the energy endpoint and sensors."""
    hass.config_entries.async_update_entry(config_entry, options={ENABLE_ENERGY: False})
    api.async_get_consumptions_sequences.return_value = [CH_ENERGY_SEQUENCE]

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    api.async_get_consumptions_sequences.assert_not_called()
    assert runtime_data(hass).energy_coordinator is None
    assert hass.states.get(CH_ENERGY) is None
    assert hass.states.get(ERRORS_COUNT) is not None


async def test_bus_errors_polling_can_be_disabled(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test the bus errors option skips the bus errors endpoint and sensor."""
    hass.config_entries.async_update_entry(
        config_entry, options={ENABLE_BUS_ERRORS: False}
    )

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    api.async_get_bus_errors.assert_not_called()
    assert runtime_data(hass).bus_errors_coordinator is None
    assert hass.states.get(ERRORS_COUNT) is None
    assert hass.states.get(CLIMATE) is not None


async def test_unload_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the entry unloads and drops its data."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED
    assert not hasattr(init_integration, "runtime_data")
    assert hass.states.get(HEATING_PUMP).state == STATE_UNAVAILABLE


async def test_setup_login_refused_starts_reauth(
    hass: HomeAssistant, mock_ariston: MagicMock, config_entry: MockConfigEntry
) -> None:
    """Test a refused login fails setup and asks for a new login."""
    mock_ariston.async_connect.return_value = False

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_setup_no_device_retries_setup(
    hass: HomeAssistant, mock_ariston: MagicMock, config_entry: MockConfigEntry
) -> None:
    """Test setup is retried when the cloud does not list the device."""
    mock_ariston.async_hello.return_value = None

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


def login_error(cause: Exception) -> ConnectionException:
    """Return the error a login raises: an empty one that wraps the cause."""
    error = ConnectionException()
    error.__cause__ = cause
    return error


@pytest.mark.parametrize(
    "error",
    [
        login_error(ConnectionException(401)),
        ConnectionException("Login failed (password changed?)"),
    ],
    ids=["login-401", "login-failed"],
)
async def test_setup_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    error: ConnectionException,
) -> None:
    """Test an auth error at login asks for a new login, without a traceback."""
    mock_ariston.async_connect.side_effect = error

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
    assert tracebacks(caplog) == []


@pytest.mark.parametrize(
    ("method", "error"),
    [
        ("async_connect", login_error(ConnectionException(500))),
        ("async_connect", login_error(ConnectionException(429))),
        ("async_connect", login_error(aiohttp.ClientConnectionError())),
        ("async_hello", ConnectionException(502)),
        ("async_hello", aiohttp.ClientError()),
        ("async_hello", TimeoutError()),
    ],
    ids=[
        "login-500",
        "login-429",
        "login-network",
        "hello-502",
        "hello-network",
        "hello-timeout",
    ],
)
async def test_setup_cloud_error_retries_setup(
    hass: HomeAssistant,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    method: str,
    error: Exception,
) -> None:
    """Test other cloud errors retry the setup later, without a traceback."""
    getattr(mock_ariston, method).side_effect = error

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert tracebacks(caplog) == []


async def test_setup_features_error_retries_setup(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a failed features request retries the setup, without a traceback."""
    api.async_get_features_for_device.side_effect = ConnectionException(500)

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert tracebacks(caplog) == []


async def test_setup_unexpected_error_is_logged_and_retried(
    hass: HomeAssistant,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test an unexpected error is logged with its traceback and retried."""
    mock_ariston.async_hello.side_effect = ValueError("bad data")

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert tracebacks(caplog) == ["Unexpected error while setting up Ariston NET"]


async def test_setup_auth_error_in_bus_errors_starts_reauth(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test an auth error of an optional coordinator still asks for a new login."""
    api.async_get_bus_errors.side_effect = ConnectionException("Invalid token")

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_unload_failure_keeps_entry_data(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the entry data stays when the platforms fail to unload."""
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        assert not await hass.config_entries.async_unload(init_integration.entry_id)

    assert init_integration.runtime_data


@pytest.mark.parametrize(
    ("option", "value", "coordinator", "expected"),
    [
        (CONF_SCAN_INTERVAL, 30, "coordinator", timedelta(seconds=60)),
        (ENERGY_SCAN_INTERVAL, 5, "energy_coordinator", timedelta(minutes=15)),
        (BUS_ERRORS_SCAN_INTERVAL, 10, "bus_errors_coordinator", timedelta(seconds=60)),
        (CONF_SCAN_INTERVAL, 10**15, "coordinator", timedelta(days=1)),
        (ENERGY_SCAN_INTERVAL, 10**15, "energy_coordinator", timedelta(days=1)),
        (BUS_ERRORS_SCAN_INTERVAL, 10**15, "bus_errors_coordinator", timedelta(days=1)),
    ],
)
async def test_setup_moves_old_interval_into_limits(
    hass: HomeAssistant,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    option: str,
    value: int,
    coordinator: str,
    expected: timedelta,
) -> None:
    """Test an interval saved out of its limits polls at the nearest limit."""
    hass.config_entries.async_update_entry(config_entry, options={option: value})

    await setup_integration(hass, config_entry)

    assert getattr(runtime_data(hass), coordinator).update_interval == expected
