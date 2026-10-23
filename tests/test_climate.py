"""Tests for the Ariston NET climate entity."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

from ariston import AristonGalevoDevice
from ariston.const import PlantMode, ZoneMode
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

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


def set_item(properties: dict[str, Any], item_id: str, **values: Any) -> None:
    """Change one item the fake cloud sends."""
    item = next(item for item in properties["items"] if item["id"] == item_id)
    item.update(values)


async def setup_and_record_calls(
    hass: HomeAssistant, config_entry: MockConfigEntry, device: AristonGalevoDevice
) -> AsyncMock:
    """Set the entry up and record plant and zone mode calls in order."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    calls = AsyncMock()
    device.async_set_plant_mode = calls.plant_mode
    device.async_set_zone_mode = calls.zone_mode
    return calls


@pytest.mark.parametrize(
    ("hvac_mode", "plant_mode_options", "zone_mode_options", "expected_calls"),
    [
        (
            HVACMode.HEAT,
            [0, 1, 2, 4, 5],
            [2, 3],
            [
                call.plant_mode(PlantMode.HEATING_ONLY),
                call.zone_mode(ZoneMode.MANUAL, 1),
            ],
        ),
        (
            HVACMode.HEAT,
            [0, 1, 4, 5],
            [2, 3],
            [call.plant_mode(PlantMode.WINTER), call.zone_mode(ZoneMode.MANUAL, 1)],
        ),
        (
            HVACMode.HEAT,
            [0, 1, 2, 4, 5],
            [1, 2, 3],
            [
                call.plant_mode(PlantMode.HEATING_ONLY),
                call.zone_mode(ZoneMode.MANUAL_NIGHT, 1),
            ],
        ),
        (
            HVACMode.AUTO,
            [0, 1, 2, 4, 5],
            [2, 3],
            [
                call.plant_mode(PlantMode.HEATING_ONLY),
                call.zone_mode(ZoneMode.TIME_PROGRAM, 1),
            ],
        ),
        (
            HVACMode.COOL,
            [0, 1, 2, 3, 5],
            [1, 2, 3],
            [
                call.plant_mode(PlantMode.COOLING),
                call.zone_mode(ZoneMode.MANUAL_NIGHT, 1),
            ],
        ),
    ],
    ids=[
        "heat",
        "heat-no-heating-only",
        "heat-manual-night",
        "auto",
        "cool-manual-night",
    ],
)
async def test_hvac_mode_from_off_matches_device_options(
    hass: HomeAssistant,
    properties: dict[str, Any],
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    hvac_mode: HVACMode,
    plant_mode_options: list[int],
    zone_mode_options: list[int],
    expected_calls: list,
) -> None:
    """Test turning on from plant OFF picks modes from the device options."""
    set_item(
        properties, "PlantMode", value=PlantMode.OFF.value, options=plant_mode_options
    )
    set_item(properties, "ZoneMode", options=zone_mode_options)
    calls = await setup_and_record_calls(hass, config_entry, device)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: hvac_mode},
        blocking=True,
    )

    assert calls.mock_calls == expected_calls


@pytest.mark.parametrize(
    ("plant_mode", "zone_mode", "preset", "expected_calls"),
    [
        (
            PlantMode.COOLING_ONLY,
            ZoneMode.TIME_PROGRAM,
            "Winter",
            [call.zone_mode(ZoneMode.MANUAL, 1), call.plant_mode(PlantMode.WINTER)],
        ),
        (
            PlantMode.WINTER,
            ZoneMode.MANUAL,
            "Off",
            [call.plant_mode(PlantMode.OFF), call.zone_mode(ZoneMode.OFF, 1)],
        ),
        (
            PlantMode.OFF,
            ZoneMode.OFF,
            "Winter",
            [call.plant_mode(PlantMode.WINTER), call.zone_mode(ZoneMode.MANUAL, 1)],
        ),
        (
            PlantMode.OFF,
            ZoneMode.OFF,
            "Summer",
            [call.plant_mode(PlantMode.SUMMER)],
        ),
        (
            PlantMode.SUMMER,
            ZoneMode.TIME_PROGRAM,
            "Heating only",
            [call.plant_mode(PlantMode.HEATING_ONLY)],
        ),
    ],
    ids=["leave-cooling", "off", "on-after-off", "summer-after-off", "zone-already-on"],
)
async def test_preset_sets_plant_and_zone_mode(
    hass: HomeAssistant,
    properties: dict[str, Any],
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    plant_mode: PlantMode,
    zone_mode: ZoneMode,
    preset: str,
    expected_calls: list,
) -> None:
    """Test a preset sets the plant mode and keeps the zone usable."""
    set_item(properties, "PlantMode", value=plant_mode.value)
    set_item(properties, "ZoneMode", value=zone_mode.value, options=[0, 2, 3])
    calls = await setup_and_record_calls(hass, config_entry, device)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_PRESET_MODE: preset},
        blocking=True,
    )

    assert calls.mock_calls == expected_calls
