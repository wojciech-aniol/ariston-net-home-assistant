"""Tests for the Ariston NET climate entity."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from ariston import AristonGalevoDevice
from ariston.const import PlantMode
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

from .conftest import PLANT_MODE_TEXTS

CLIMATE = "climate.nimbus"


@pytest.mark.parametrize(
    ("plant_mode_options", "expected_plant_mode"),
    [([0, 1, 2, 4, 5], PlantMode.OFF), ([0, 1, 2], PlantMode.SUMMER)],
    ids=["plant-off", "no-plant-off"],
)
async def test_hvac_mode_off_uses_plant_mode(
    hass: HomeAssistant,
    properties: dict[str, Any],
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    plant_mode_options: list[int],
    expected_plant_mode: PlantMode,
) -> None:
    """Test OFF is offered and set through the plant mode."""
    plant_mode = properties["items"][0]
    plant_mode["options"] = plant_mode_options
    plant_mode["optTexts"] = PLANT_MODE_TEXTS[: len(plant_mode_options)]
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert not device.is_zone_mode_options_contains_off(1)
    state = hass.states.get(CLIMATE)
    assert state.state == HVACMode.HEAT
    assert HVACMode.OFF in state.attributes[ATTR_HVAC_MODES]

    device.async_set_plant_mode = AsyncMock()
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )

    device.async_set_plant_mode.assert_awaited_once_with(expected_plant_mode)
