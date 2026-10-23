"""Tests for setting up Ariston NET."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

from ariston.ariston_api import ConnectionException
from ariston.const import ConsumptionTimeInterval, ConsumptionType
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import (
    BUS_ERRORS_COORDINATOR,
    DOMAIN,
    ENABLE_BUS_ERRORS,
    ENABLE_ENERGY,
    ENERGY_COORDINATOR,
)

from .conftest import GATEWAY

CLIMATE = "climate.nimbus"
WATER_HEATER = "water_heater.nimbus"
HEATING_PUMP = "binary_sensor.nimbus_ariston_net_is_heating_pump_on"
PLANT_MODE = "select.nimbus_ariston_net_plant_mode"
DHW_CURRENT_TEMP = "sensor.nimbus_ariston_net_dhw_current_temperature"
ERRORS_COUNT = "sensor.nimbus_ariston_net_errors_count"
CH_ENERGY = "sensor.nimbus_ariston_net_central_heating_total_energy_consumption"

CH_ENERGY_SEQUENCE: dict[str, Any] = {
    "k": ConsumptionType.CENTRAL_HEATING_TOTAL_ENERGY.value,
    "p": ConsumptionTimeInterval.LAST_DAY.value,
    "v": [1.5, 2.5],
}


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
