"""Tests for the actions of the VELIS Evo family: Evo, Evo2, Andris2, Lux and Lux2."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from ariston.const import (
    EvoPlantMode,
    LuxPlantMode,
    PlantData,
    VelisPlantMode,
    WaterHeaterMode,
)
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.water_heater import (
    ATTR_OPERATION_MODE,
    DOMAIN as WATER_HEATER_DOMAIN,
    SERVICE_SET_OPERATION_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import GATEWAY, setup_integration

# VELIS types the library builds as AristonEvoDevice or a subclass.
MED_TYPES = ["evo2", "andris2", "lux", "lux2"]

WATER_HEATER = "water_heater.velis"
ANTI_LEGIONELLA = "MedAntilegionellaOnOff"
MAX_SETPOINT = "MedMaxSetpointTemperature"

TURN_ON_OFF = pytest.mark.parametrize(
    ("service", "value"),
    [(SERVICE_TURN_ON, True), (SERVICE_TURN_OFF, False)],
    ids=["on", "off"],
)


async def turn(hass: HomeAssistant, domain: str, service: str, entity_id: str) -> None:
    """Turn an entity on or off."""
    await hass.services.async_call(
        domain, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )


@TURN_ON_OFF
@pytest.mark.parametrize("device_type", ["evo", *MED_TYPES])
async def test_eco_switch_sends_eco_mode(
    hass: HomeAssistant,
    api: MagicMock,
    device_data: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    service: str,
    value: bool,
) -> None:
    """Test the eco mode switch sends the new value."""
    device_data["plant_data"]["eco"] = not value
    await setup_integration(hass, config_entry)

    await turn(hass, SWITCH_DOMAIN, service, "switch.velis_ariston_net_eco_mode")

    api.async_set_evo_eco_mode.assert_awaited_once_with(GATEWAY, value)


@TURN_ON_OFF
@pytest.mark.parametrize(
    ("device_type", "plant_data"),
    [
        ("evo", PlantData.PD),
        *((device_type, PlantData.Med) for device_type in MED_TYPES),
    ],
)
async def test_power_switch_sends_power(
    hass: HomeAssistant,
    api: MagicMock,
    device_data: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    plant_data: PlantData,
    service: str,
    value: bool,
) -> None:
    """Test the power switch sends the new value for the plant data of the type."""
    device_data["plant_data"]["on"] = not value
    await setup_integration(hass, config_entry)

    await turn(hass, SWITCH_DOMAIN, service, "switch.velis_ariston_net_power")

    api.async_set_velis_power.assert_awaited_once_with(plant_data, GATEWAY, value)


@TURN_ON_OFF
@pytest.mark.parametrize("device_type", MED_TYPES)
async def test_anti_legionella_switch_sends_plant_setting(
    hass: HomeAssistant,
    api: MagicMock,
    device_data: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    service: str,
    value: bool,
) -> None:
    """Test the anti legionella switch sends the new and old values as numbers."""
    device_data["plant_settings"][ANTI_LEGIONELLA] = not value
    await setup_integration(hass, config_entry)

    await turn(hass, SWITCH_DOMAIN, service, "switch.velis_ariston_net_anti_legionella")

    api.async_set_velis_plant_setting.assert_awaited_once_with(
        PlantData.Med, GATEWAY, ANTI_LEGIONELLA, float(value), float(not value)
    )


@TURN_ON_OFF
@pytest.mark.parametrize("device_type", ["lux2"])
async def test_power_option_switch_sends_power_option(
    hass: HomeAssistant,
    api: MagicMock,
    device_data: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    service: str,
    value: bool,
) -> None:
    """Test the Lux2 power option switch sends the new value."""
    device_data["plant_data"]["pwrOpt"] = not value
    await setup_integration(hass, config_entry)

    await turn(hass, SWITCH_DOMAIN, service, "switch.velis_ariston_net_power_option")

    api.async_set_lux_power_option.assert_awaited_once_with(GATEWAY, value)


@pytest.mark.parametrize("device_type", MED_TYPES)
async def test_max_setpoint_number_sends_plant_setting(
    hass: HomeAssistant, api: MagicMock, init_integration: MockConfigEntry
) -> None:
    """Test the max setpoint number sends the new and old values."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.velis_ariston_net_max_setpoint_temperature",
            ATTR_VALUE: 75,
        },
        blocking=True,
    )

    api.async_set_velis_plant_setting.assert_awaited_once_with(
        PlantData.Med, GATEWAY, MAX_SETPOINT, 75.0, 70.0
    )


@pytest.mark.parametrize("device_type", ["evo"])
async def test_showers_number_sends_number_of_showers(
    hass: HomeAssistant, api: MagicMock, init_integration: MockConfigEntry
) -> None:
    """Test the Evo requested showers number sends a whole number."""
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.velis_ariston_net_requested_number_of_showers",
            ATTR_VALUE: 3,
        },
        blocking=True,
    )

    api.async_set_evo_number_of_showers.assert_awaited_once_with(GATEWAY, 3)


@pytest.mark.parametrize("device_type", ["evo"])
@pytest.mark.parametrize(
    ("option", "expected_mode"),
    [("PROGRAM", VelisPlantMode.PROGRAM), ("NIGHT", VelisPlantMode.NIGHT)],
)
async def test_operation_mode_select_sends_evo_mode(
    hass: HomeAssistant,
    api: MagicMock,
    init_integration: MockConfigEntry,
    option: str,
    expected_mode: VelisPlantMode,
) -> None:
    """Test the Evo operation mode select sends the mode of the option."""
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: "select.velis_ariston_net_operation_mode",
            ATTR_OPTION: option,
        },
        blocking=True,
    )

    api.async_set_evo_mode.assert_awaited_once_with(GATEWAY, expected_mode)


@pytest.mark.parametrize("device_type", MED_TYPES)
async def test_water_heater_set_temperature_sends_evo_temperature(
    hass: HomeAssistant, api: MagicMock, init_integration: MockConfigEntry
) -> None:
    """Test the water heater target temperature goes to the cloud."""
    await hass.services.async_call(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: WATER_HEATER, ATTR_TEMPERATURE: 60},
        blocking=True,
    )

    api.async_set_evo_temperature.assert_awaited_once_with(GATEWAY, 60)


@pytest.mark.parametrize(
    ("device_type", "operation_mode", "expected_mode"),
    [
        ("evo2", "PROGRAM", EvoPlantMode.PROGRAM),
        ("andris2", "PROGRAM", EvoPlantMode.PROGRAM),
        ("lux", "BOOST", LuxPlantMode.BOOST),
        ("lux2", "PROGRAM", EvoPlantMode.PROGRAM),
    ],
)
async def test_water_heater_set_operation_mode_sends_evo_mode(
    hass: HomeAssistant,
    api: MagicMock,
    init_integration: MockConfigEntry,
    operation_mode: str,
    expected_mode: WaterHeaterMode,
) -> None:
    """Test the water heater operation mode goes to the cloud as the mode of the type."""
    await hass.services.async_call(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_OPERATION_MODE,
        {ATTR_ENTITY_ID: WATER_HEATER, ATTR_OPERATION_MODE: operation_mode},
        blocking=True,
    )

    api.async_set_evo_mode.assert_awaited_once_with(GATEWAY, expected_mode)


@TURN_ON_OFF
@pytest.mark.parametrize("device_type", MED_TYPES)
async def test_water_heater_turn_on_off_sends_power(
    hass: HomeAssistant,
    api: MagicMock,
    device_data: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    service: str,
    value: bool,
) -> None:
    """Test turning the water heater on or off sends the power."""
    device_data["plant_data"]["on"] = not value
    await setup_integration(hass, config_entry)

    await turn(hass, WATER_HEATER_DOMAIN, service, WATER_HEATER)

    api.async_set_velis_power.assert_awaited_once_with(PlantData.Med, GATEWAY, value)


@TURN_ON_OFF
@pytest.mark.parametrize("device_type", MED_TYPES)
async def test_water_heater_turn_on_off_updates_power_switch(
    hass: HomeAssistant,
    device_data: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    service: str,
    value: bool,
) -> None:
    """Test the power switch shows the new power at once."""
    device_data["plant_data"]["on"] = not value
    await setup_integration(hass, config_entry)

    await turn(hass, WATER_HEATER_DOMAIN, service, WATER_HEATER)

    expected_state = STATE_ON if value else STATE_OFF
    assert hass.states.get("switch.velis_ariston_net_power").state == expected_state
