"""Tests for the entities of a BSB device."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from ariston_net_api.const import BsbOperativeMode, BsbZoneMode
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE as CLIMATE_SET_TEMPERATURE,
    HVACAction,
    HVACMode,
)
from homeassistant.components.water_heater import (
    ATTR_OPERATION_MODE,
    DOMAIN as WATER_HEATER_DOMAIN,
    SERVICE_SET_OPERATION_MODE,
    SERVICE_SET_TEMPERATURE as WATER_HEATER_SET_TEMPERATURE,
    WaterHeaterEntityFeature,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import GATEWAY, setup_integration

CLIMATE = "climate.boiler"
HEAT_PUMP = "binary_sensor.boiler_heat_pump"
WATER_HEATER = "water_heater.boiler"
ZONE = 1


@pytest.fixture
def device_type() -> str:
    """Return the BSB device type."""
    return "bsb"


@pytest.mark.parametrize(
    ("hvac_mode", "start_mode", "expected_mode"),
    [
        (HVACMode.OFF, BsbZoneMode.MANUAL, BsbZoneMode.OFF),
        (HVACMode.AUTO, BsbZoneMode.MANUAL, BsbZoneMode.TIME_PROGRAM),
        (HVACMode.HEAT, BsbZoneMode.TIME_PROGRAM, BsbZoneMode.MANUAL),
        (HVACMode.HEAT, BsbZoneMode.OFF, BsbZoneMode.MANUAL),
    ],
)
async def test_climate_hvac_mode_sends_bsb_zone_mode(
    hass: HomeAssistant,
    api: MagicMock,
    device_data: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    hvac_mode: HVACMode,
    start_mode: BsbZoneMode,
    expected_mode: BsbZoneMode,
) -> None:
    """Test each HVAC mode sends its BSB zone mode, with the old one."""
    device_data["plant_data"]["zones"][str(ZONE)]["mode"]["value"] = start_mode.value
    await setup_integration(hass, config_entry)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: hvac_mode},
        blocking=True,
    )

    api.async_set_bsb_zone_mode.assert_awaited_once_with(
        GATEWAY, ZONE, expected_mode, start_mode, False
    )


async def test_climate_set_temperature_sends_comfort_temp(
    hass: HomeAssistant, api: MagicMock, init_integration: MockConfigEntry
) -> None:
    """Test the target temperature goes to the zone with its reduced temp."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        CLIMATE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_TEMPERATURE: 22.5},
        blocking=True,
    )

    api.async_set_bsb_zone_temperature.assert_awaited_once_with(
        GATEWAY, ZONE, 22.5, 17.0, 21.0, 17.0, False
    )


async def test_water_heater_set_temperature_sends_comfort_temp(
    hass: HomeAssistant, api: MagicMock, init_integration: MockConfigEntry
) -> None:
    """Test the target temperature goes to the cloud with the reduced temp."""
    await hass.services.async_call(
        WATER_HEATER_DOMAIN,
        WATER_HEATER_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: WATER_HEATER, ATTR_TEMPERATURE: 55},
        blocking=True,
    )

    api.async_set_bsb_temperature.assert_awaited_once_with(
        GATEWAY, 55, 40.0, 50.0, 40.0
    )


async def test_water_heater_set_operation_mode_sends_bsb_mode(
    hass: HomeAssistant, api: MagicMock, init_integration: MockConfigEntry
) -> None:
    """Test the operation mode text goes to the cloud as a BSB mode."""
    await hass.services.async_call(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_OPERATION_MODE,
        {ATTR_ENTITY_ID: WATER_HEATER, ATTR_OPERATION_MODE: "OFF"},
        blocking=True,
    )

    api.async_set_bsb_mode.assert_awaited_once_with(GATEWAY, BsbOperativeMode.OFF)


async def test_water_heater_has_no_on_off(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test a BSB water heater does not offer on and off, which is for VELIS only."""
    state = hass.states.get(WATER_HEATER)

    assert state.attributes[ATTR_SUPPORTED_FEATURES] == (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )


@pytest.mark.parametrize(
    ("hp_on", "expected_state"), [(True, STATE_ON), (False, STATE_OFF)]
)
async def test_heat_pump_follows_hp_on(
    hass: HomeAssistant,
    device_data: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    hp_on: bool,
    expected_state: str,
) -> None:
    """Test the heat pump sensor shows hpOn when the cloud sends it."""
    device_data["plant_data"]["hpOn"] = hp_on
    await setup_integration(hass, config_entry)

    assert hass.states.get(HEAT_PUMP).state == expected_state


async def test_heat_pump_has_galevo_unique_id(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device_data: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test the BSB heat pump sensor uses the unique ID format of GALEVO."""
    device_data["plant_data"]["hpOn"] = True
    await setup_integration(hass, config_entry)

    entry = entity_registry.async_get(HEAT_PUMP)
    assert entry.unique_id == f"{GATEWAY}-Ariston NET is heating pump on"


async def test_climate_without_room_sensor_has_no_current_temperature(
    hass: HomeAssistant,
    device_data: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test a zone without a room sensor shows no current temperature."""
    device_data["plant_data"]["zones"][str(ZONE)]["hasRoomSens"] = False
    await setup_integration(hass, config_entry)

    assert hass.states.get(CLIMATE).attributes[ATTR_CURRENT_TEMPERATURE] is None


@pytest.mark.parametrize(
    ("heat_request", "expected_action"),
    [(True, HVACAction.HEATING), (False, HVACAction.IDLE)],
)
async def test_hvac_action_follows_zone_request(
    hass: HomeAssistant,
    device_data: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    heat_request: bool,
    expected_action: HVACAction,
) -> None:
    """Test the zone heats only while it asks, even with the flame on."""
    device_data["plant_data"]["zones"][str(ZONE)]["heatOrCoolReq"] = heat_request
    await setup_integration(hass, config_entry)

    assert hass.states.get(CLIMATE).attributes[ATTR_HVAC_ACTION] == expected_action
