"""Tests for setting up Ariston NET."""

from __future__ import annotations

import copy
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from ariston import AristonBsbDevice, AristonGalevoDevice
from ariston.ariston_api import ConnectionException
from ariston.const import (
    ARISTON_API_URL,
    ARISTON_USER_AGENT,
    ConsumptionTimeInterval,
    ConsumptionType,
)
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import (
    ATTR_DEVICE_ID,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import (
    API_URL_SETTING,
    API_USER_AGENT,
    BUS_ERRORS_COORDINATOR,
    DOMAIN,
    ENABLE_BUS_ERRORS,
    ENABLE_ENERGY,
    ENERGY_COORDINATOR,
)

from .conftest import CLOUD_DEVICE, GATEWAY

CLIMATE = "climate.nimbus"
WATER_HEATER = "water_heater.nimbus"
HEATING_PUMP = "binary_sensor.nimbus_ariston_net_is_heating_pump_on"
PLANT_MODE = "select.nimbus_ariston_net_plant_mode"
DHW_CURRENT_TEMP = "sensor.nimbus_ariston_net_dhw_current_temperature"
ERRORS_COUNT = "sensor.nimbus_ariston_net_errors_count"
CH_ENERGY = "sensor.nimbus_ariston_net_central_heating_total_energy_consumption"
HOLIDAY = "binary_sensor.nimbus_ariston_net_holiday_mode"

CH_ENERGY_SEQUENCE: dict[str, Any] = {
    "k": ConsumptionType.CENTRAL_HEATING_TOTAL_ENERGY.value,
    "p": ConsumptionTimeInterval.LAST_DAY.value,
    "v": [1.5, 2.5],
}


def device_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Return the device registry ID of the entry's device."""
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return device.id


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


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
) -> None:
    """Test setup is retried when the device state can't be read."""
    api.async_get_properties.side_effect = ConnectionException(500)

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


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
    assert not hass.data[DOMAIN][GATEWAY][ENERGY_COORDINATOR].last_update_success
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
    await hass.data[DOMAIN][GATEWAY][ENERGY_COORDINATOR].async_refresh()
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
    await hass.data[DOMAIN][GATEWAY][ENERGY_COORDINATOR].async_refresh()
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
    assert not hass.data[DOMAIN][GATEWAY][BUS_ERRORS_COORDINATOR].last_update_success
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
    assert not hass.data[DOMAIN][GATEWAY][ENERGY_COORDINATOR]
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
    assert not hass.data[DOMAIN][GATEWAY][BUS_ERRORS_COORDINATOR]
    assert hass.states.get(ERRORS_COUNT) is None
    assert hass.states.get(CLIMATE) is not None


async def test_unload_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the entry unloads and drops its data."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED
    assert GATEWAY not in hass.data[DOMAIN]
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


async def test_setup_no_device_fails_without_retry(
    hass: HomeAssistant, mock_ariston: MagicMock, config_entry: MockConfigEntry
) -> None:
    """Test setup fails for good when the cloud has no such device."""
    mock_ariston.async_hello.return_value = None

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


async def test_set_item_by_id_service_calls_device(
    hass: HomeAssistant,
    device: AristonGalevoDevice,
    init_integration: MockConfigEntry,
) -> None:
    """Test the set item service passes the item, value and zone on."""
    device.async_set_item_by_id = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        "set_item_by_id",
        {
            ATTR_DEVICE_ID: device_id(hass, init_integration),
            "item_id": "ZoneComfortTemp",
            "zone": 1,
            "value": "21.5",
        },
        blocking=True,
    )

    device.async_set_item_by_id.assert_awaited_once_with("ZoneComfortTemp", 21.5, 1)


async def test_create_vacation_service_sets_end_date(
    hass: HomeAssistant, api: MagicMock, init_integration: MockConfigEntry
) -> None:
    """Test the vacation service sends the end date and turns holiday on."""
    await hass.services.async_call(
        DOMAIN,
        "create_vacation",
        {ATTR_DEVICE_ID: device_id(hass, init_integration), "end_date": "2026-11-01"},
        blocking=True,
    )

    api.async_set_holiday.assert_awaited_once_with(GATEWAY, "2026-11-01T00:00:00")
    state = hass.states.get(HOLIDAY)
    assert state.state == STATE_ON
    assert state.attributes["holiday"] == "2026-11-01T00:00:00"


async def test_create_vacation_service_without_date_ends_holiday(
    hass: HomeAssistant,
    api: MagicMock,
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test the vacation service with no date turns holiday off."""
    holiday = next(item for item in properties["items"] if item["id"] == "Holiday")
    holiday.update(value=True, expiresOn="2026-11-01T00:00:00")
    await setup_integration(hass, config_entry)
    assert hass.states.get(HOLIDAY).state == STATE_ON

    await hass.services.async_call(
        DOMAIN,
        "create_vacation",
        {ATTR_DEVICE_ID: device_id(hass, config_entry)},
        blocking=True,
    )

    api.async_set_holiday.assert_awaited_once_with(GATEWAY, None)
    state = hass.states.get(HOLIDAY)
    assert state.state == STATE_OFF
    assert "holiday" not in state.attributes


async def test_services_missing_for_other_systems(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test the GALEVO services are not registered for a BSB device."""
    api.async_get_bsb_plant_data = AsyncMock(return_value={})
    mock_ariston.async_hello.return_value = AristonBsbDevice(
        api, copy.deepcopy(CLOUD_DEVICE) | {"sys": 5}
    )

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert not hass.services.has_service(DOMAIN, "set_item_by_id")
    assert not hass.services.has_service(DOMAIN, "create_vacation")


async def test_unload_failure_keeps_entry_data(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the entry data stays when the platforms fail to unload."""
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        assert not await hass.config_entries.async_unload(init_integration.entry_id)

    assert GATEWAY in hass.data[DOMAIN]
