"""Tests for the Ariston NET plant mode select."""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock

from ariston import AristonGalevoDevice
from ariston.const import PlantMode
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.climate import ATTR_PRESET_MODE, HVACMode
from homeassistant.components.select import (
    ATTR_OPTION,
    ATTR_OPTIONS,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

from .conftest import GATEWAY, PLANT_MODE_TEXTS

PLANT_MODE = "select.nimbus_ariston_net_plant_mode"
CLIMATE = "climate.nimbus"


async def select_plant_mode(hass: HomeAssistant, option: str) -> None:
    """Select a plant mode option."""
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: PLANT_MODE, ATTR_OPTION: option},
        blocking=True,
    )


async def test_plant_mode_state(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test options and current option come from the device."""
    state = hass.states.get(PLANT_MODE)

    assert state.state == "Winter"
    assert state.attributes[ATTR_OPTIONS] == PLANT_MODE_TEXTS


@pytest.mark.parametrize(
    ("option", "plant_mode"),
    [
        ("Summer", PlantMode.SUMMER),
        ("Heating only", PlantMode.HEATING_ONLY),
        ("Cooling only", PlantMode.COOLING_ONLY),
        ("Off", PlantMode.OFF),
    ],
)
async def test_select_plant_mode(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device: AristonGalevoDevice,
    option: str,
    plant_mode: PlantMode,
) -> None:
    """Test the option maps to the plant mode by its option value."""
    device.async_set_plant_mode = AsyncMock()

    await select_plant_mode(hass, option)

    device.async_set_plant_mode.assert_awaited_once_with(plant_mode)


async def test_select_plant_mode_updates_climate(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    api: MagicMock,
) -> None:
    """Test selecting Summer sends it to the cloud and updates the climate."""
    assert hass.states.get(CLIMATE).state == HVACMode.HEAT

    await select_plant_mode(hass, "Summer")

    api.async_set_property.assert_awaited_once_with(
        GATEWAY, 0, ANY, "PlantMode", PlantMode.SUMMER.value, PlantMode.WINTER.value, "si"
    )
    assert hass.states.get(PLANT_MODE).state == "Summer"
    climate = hass.states.get(CLIMATE)
    assert climate.state == HVACMode.OFF
    assert climate.attributes[ATTR_PRESET_MODE] == "Summer"
