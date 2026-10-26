"""Tests for the Ariston NET sensors of a GALEVO device."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from ariston_net_api.ariston_api import ConnectionException
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import (
    ATTR_LAST_RESET,
    ATTR_STATE_CLASS,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import ATTR_ERRORS
from custom_components.ariston_net.coordinator import DeviceDataUpdateCoordinator
from custom_components.ariston_net.sensor import (
    AristonSensor,
    AristonSensorEntityDescription,
)

from .conftest import (
    BUS_ERRORS,
    METERING_BINS,
    METERING_SENSORS,
    metering_data,
    refresh_energy,
    refresh_metering,
    runtime_data,
    set_item,
    setup_integration,
)

SIGNAL_STRENGTH = "sensor.nimbus_signal_strength"
DHW_CURRENT_TEMP = "sensor.nimbus_hot_water_temperature"
CH_ENERGY = "sensor.nimbus_heating_energy"
CH_GAS = "sensor.nimbus_heating_gas_last_month"
ERRORS_COUNT = "sensor.nimbus_bus_errors"
HEATING_TODAY = "sensor.nimbus_heating_energy_produced_today"
HEATING_THIS_MONTH = "sensor.nimbus_heating_energy_produced_this_month"
COOLING_TODAY = "sensor.nimbus_cooling_energy_produced_today"
COOLING_THIS_MONTH = "sensor.nimbus_cooling_energy_produced_this_month"
HEATING_COP_YESTERDAY = "sensor.nimbus_heating_cop_yesterday"
DHW_COP_THIS_MONTH = "sensor.nimbus_hot_water_cop_this_month"
HEATING_USED_YESTERDAY = ("ConsumedElectricity", "Heating", "PreviousDay")


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
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


async def test_signal_strength_is_disabled_by_default(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Test a new install creates the signal strength sensor disabled."""
    entry = entity_registry.async_get(SIGNAL_STRENGTH)

    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(SIGNAL_STRENGTH) is None


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


@pytest.fixture
async def energy_late(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    full_galevo: MagicMock,
    config_entry: MockConfigEntry,
) -> DeviceDataUpdateCoordinator:
    """Set the entry up while the energy data fails, and return its coordinator."""
    api.async_get_consumptions_sequences.side_effect = ConnectionException(500)
    await setup_integration(hass, config_entry)
    api.async_get_consumptions_sequences.side_effect = None
    return runtime_data(hass).energy_coordinator


def listener_names(coordinator: DeviceDataUpdateCoordinator) -> list[str]:
    """Return the names of the coordinator's listener callbacks."""
    return [listener.__name__ for listener, _ in coordinator._listeners.values()]


async def test_energy_sensors_added_once(
    hass: HomeAssistant, energy_late: DeviceDataUpdateCoordinator
) -> None:
    """Test energy sensors added late are not added again on the next refresh."""
    await energy_late.async_refresh()
    await hass.async_block_till_done()
    sensors = hass.states.async_entity_ids("sensor")
    assert CH_ENERGY in sensors

    await energy_late.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.async_entity_ids("sensor") == sensors


async def test_energy_sensors_listener_removed_after_adding(
    hass: HomeAssistant, energy_late: DeviceDataUpdateCoordinator
) -> None:
    """Test the late energy sensor listener goes away once the sensors are added."""
    assert "async_add_energy_sensors" in listener_names(energy_late)

    await energy_late.async_refresh()
    await hass.async_block_till_done()

    assert CH_ENERGY in hass.states.async_entity_ids("sensor")
    assert "async_add_energy_sensors" not in listener_names(energy_late)


async def test_energy_sensors_wait_while_energy_fails(
    hass: HomeAssistant, energy_late: DeviceDataUpdateCoordinator
) -> None:
    """Test an update without energy data adds no sensor and keeps waiting."""
    energy_late.async_update_listeners()
    await hass.async_block_till_done()

    assert CH_ENERGY not in hass.states.async_entity_ids("sensor")
    assert "async_add_energy_sensors" in listener_names(energy_late)


@pytest.mark.parametrize("energy_arrived", [False, True], ids=["waiting", "added"])
async def test_energy_late_entry_unloads(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    energy_late: DeviceDataUpdateCoordinator,
    energy_arrived: bool,
) -> None:
    """Test the entry unloads whether or not the late energy sensors were added."""
    if energy_arrived:
        await energy_late.async_refresh()
        await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_errors_count_lists_bus_errors(
    hass: HomeAssistant, init_full_integration: MockConfigEntry
) -> None:
    """Test the errors sensor counts the bus errors and lists them."""
    state = hass.states.get(ERRORS_COUNT)

    assert state.state == "1"
    assert state.attributes[ATTR_ERRORS] == BUS_ERRORS


@pytest.mark.parametrize(
    ("entity_id", "expected"),
    [
        (HEATING_TODAY, "3.5"),
        (HEATING_THIS_MONTH, "62.5"),
        (COOLING_THIS_MONTH, "4.0"),
        (HEATING_COP_YESTERDAY, "4.0"),
        (DHW_COP_THIS_MONTH, "3.5"),
    ],
)
async def test_metering_sensor_shows_metering_totals(
    hass: HomeAssistant,
    init_metering_integration: MockConfigEntry,
    entity_id: str,
    expected: str,
) -> None:
    """Test a heat produced or COP sensor shows the sums of its bins."""
    assert hass.states.get(entity_id).state == expected


@pytest.mark.parametrize(
    ("entity_id", "expected"),
    [
        (HEATING_TODAY, None),
        (HEATING_THIS_MONTH, SensorStateClass.TOTAL_INCREASING),
    ],
)
async def test_produced_energy_statistics_only_for_this_month(
    hass: HomeAssistant,
    init_metering_integration: MockConfigEntry,
    entity_id: str,
    expected: SensorStateClass | None,
) -> None:
    """Test only "this month" keeps statistics, and it has no reset time."""
    state = hass.states.get(entity_id)

    assert state.attributes.get(ATTR_STATE_CLASS) == expected
    assert ATTR_LAST_RESET not in state.attributes


@pytest.mark.parametrize(
    "bins",
    [
        METERING_BINS | {HEATING_USED_YESTERDAY: [0.0, 0.0]},
        METERING_BINS | {HEATING_USED_YESTERDAY: [0.25, 0.2]},
        {
            key: bins
            for key, bins in METERING_BINS.items()
            if key != HEATING_USED_YESTERDAY
        },
    ],
    ids=["zero", "little", "missing"],
)
async def test_cop_unknown_with_too_little_electricity_used(
    hass: HomeAssistant,
    api: MagicMock,
    init_metering_integration: MockConfigEntry,
    bins: dict[tuple[str, str, str], list[float]],
) -> None:
    """Test a COP has no value below half a kWh of electricity used."""
    api.async_get_metering_data.return_value = metering_data(bins)

    await refresh_metering(hass)

    assert hass.states.get(HEATING_COP_YESTERDAY).state == STATE_UNKNOWN


async def test_cop_sensors_skipped_for_hybrid_plant(
    hass: HomeAssistant,
    features: dict[str, Any],
    mock_ariston: MagicMock,
    metering: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test a hybrid plant gets heat produced but no COP, as gas may make its heat."""
    features["hybridSys"] = True

    await setup_integration(hass, config_entry)

    assert hass.states.get(HEATING_COP_YESTERDAY) is None
    assert hass.states.get(DHW_COP_THIS_MONTH) is None
    assert hass.states.get(HEATING_TODAY).state == "3.5"


async def test_metering_sensors_added_before_metering_data(
    hass: HomeAssistant,
    api: MagicMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test the sensors exist without metering rows and show them when they come."""
    assert {hass.states.get(entity_id).state for entity_id in METERING_SENSORS} == {
        STATE_UNKNOWN
    }

    api.async_get_metering_data.return_value = metering_data(METERING_BINS)
    await refresh_metering(hass)

    assert hass.states.get(HEATING_TODAY).state == "3.5"


@pytest.mark.parametrize("options", [[0, 1, 2, 5], None], ids=["no-cooling", "unknown"])
async def test_cooling_sensors_need_a_cooling_mode(
    hass: HomeAssistant,
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    options: list[int] | None,
) -> None:
    """Test cooling sensors are skipped when the plant modes have no cooling."""
    set_item(properties, "PlantMode", options=options)

    await setup_integration(hass, config_entry)

    assert hass.states.get(COOLING_TODAY) is None
    assert hass.states.get(COOLING_THIS_MONTH) is None
    assert hass.states.get(HEATING_TODAY) is not None


async def test_metering_sensors_unavailable_while_metering_is_off(
    hass: HomeAssistant,
    api: MagicMock,
    init_metering_integration: MockConfigEntry,
) -> None:
    """Test the sensors are unavailable while the web app shows metering as off."""
    api.async_get_metering_data.return_value = metering_data(
        METERING_BINS, intensive_logs=True
    )

    await refresh_metering(hass)

    assert {hass.states.get(entity_id).state for entity_id in METERING_SENSORS} == {
        STATE_UNAVAILABLE
    }
