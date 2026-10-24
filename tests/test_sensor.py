"""Tests for the Ariston NET sensors of a GALEVO device."""

from __future__ import annotations

from unittest.mock import MagicMock

from ariston.ariston_api import ConnectionException
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import ATTR_LAST_RESET
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import ATTR_ERRORS
from custom_components.ariston_net.sensor import (
    AristonSensor,
    AristonSensorEntityDescription,
)

from .conftest import BUS_ERRORS, refresh_energy, runtime_data

SIGNAL_STRENGTH = "sensor.nimbus_ariston_net_signal_strength"
DHW_CURRENT_TEMP = "sensor.nimbus_ariston_net_dhw_current_temperature"
CH_ENERGY = "sensor.nimbus_ariston_net_central_heating_total_energy_consumption"
CH_GAS = "sensor.nimbus_ariston_net_gas_consumption_for_heating_last_month"
ERRORS_COUNT = "sensor.nimbus_ariston_net_errors_count"


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_sensor_unit_comes_from_device(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test a sensor with a unit getter shows the unit the device sends."""
    api.menu_items_request.return_value = [{"id": 119, "value": -60, "unit": "dBm"}]

    await setup_integration(hass, config_entry)

    state = hass.states.get(SIGNAL_STRENGTH)
    assert state.state == "-60"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "dBm"


@pytest.mark.parametrize(
    ("entity_id", "expected_unit"),
    [(DHW_CURRENT_TEMP, "°C"), (CH_GAS, "kWh"), (ERRORS_COUNT, "")],
)
async def test_sensor_unit_comes_from_description(
    hass: HomeAssistant,
    init_full_integration: MockConfigEntry,
    entity_id: str,
    expected_unit: str,
) -> None:
    """Test a sensor without a unit getter shows the unit of its description."""
    state = hass.states.get(entity_id)

    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == expected_unit


async def test_sensor_without_unit_has_none(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test a description with no unit gives no unit.

    No description has no unit today, so the entity is built directly.
    """
    coordinator = runtime_data(hass).coordinator
    description = AristonSensorEntityDescription(
        key="no_unit", get_native_value=lambda entity: 1
    )

    sensor = AristonSensor(coordinator, description)

    assert sensor.native_unit_of_measurement is None


async def test_total_energy_unknown_until_data_changes(
    hass: HomeAssistant,
    init_full_integration: MockConfigEntry,
) -> None:
    """Test a total energy sensor has no value and no reset before a change."""
    state = hass.states.get(CH_ENERGY)

    assert state.state == STATE_UNKNOWN
    assert ATTR_LAST_RESET not in state.attributes


async def test_total_energy_last_reset_after_data_changes(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    api: MagicMock,
    init_full_integration: MockConfigEntry,
) -> None:
    """Test a total energy sensor gets the reset time the library sets."""
    freezer.move_to("2026-10-18 12:00:00+00:00")

    await refresh_energy(hass, api)

    state = hass.states.get(CH_ENERGY)
    assert state.state == "2.5"
    # The library sets the reset one hour before the change.
    assert state.attributes[ATTR_LAST_RESET] == "2026-10-18T11:00:00+00:00"


async def test_energy_sensors_added_once(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    full_galevo: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test energy sensors added late are not added again on the next refresh."""
    api.async_get_consumptions_sequences.side_effect = ConnectionException(500)
    await setup_integration(hass, config_entry)
    energy_coordinator = runtime_data(hass).energy_coordinator
    api.async_get_consumptions_sequences.side_effect = None
    await energy_coordinator.async_refresh()
    await hass.async_block_till_done()
    sensors = hass.states.async_entity_ids("sensor")
    assert CH_ENERGY in sensors

    await energy_coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.async_entity_ids("sensor") == sensors


async def test_errors_count_lists_bus_errors(
    hass: HomeAssistant, init_full_integration: MockConfigEntry
) -> None:
    """Test the errors sensor counts the bus errors and lists them."""
    state = hass.states.get(ERRORS_COUNT)

    assert state.state == "1"
    assert state.attributes[ATTR_ERRORS] == BUS_ERRORS
