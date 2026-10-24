"""Tests for the climate and water heater actions of a BSB device."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from ariston.const import BsbOperativeMode, BsbZoneMode
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE as CLIMATE_SET_TEMPERATURE,
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
)
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import GATEWAY, setup_integration

CLIMATE = "climate.boiler"
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
        pytest.param(
            HVACMode.HEAT,
            BsbZoneMode.OFF,
            BsbZoneMode.MANUAL,
            marks=pytest.mark.xfail(
                reason="Library bug: it reads zone mode 0 as UNDEFINED", strict=True
            ),
        ),
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
