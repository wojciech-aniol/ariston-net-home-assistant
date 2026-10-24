"""Tests for the Ariston NET water heater of a GALEVO device."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from ariston import AristonGalevoDevice
from ariston.const import VelisBaseDeviceProperties
from ariston.lydos_device import AristonLydosDevice
from homeassistant.components.water_heater import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_OPERATION_LIST,
    ATTR_OPERATION_MODE,
    DATA_COMPONENT,
    DOMAIN as WATER_HEATER_DOMAIN,
    SERVICE_SET_OPERATION_MODE,
    SERVICE_SET_TEMPERATURE,
    WaterHeaterEntityFeature,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import ATTR_TARGET_TEMP_STEP
from custom_components.ariston_net.water_heater import (
    ARISTON_WATER_HEATER_TYPES,
    AristonWaterHeater,
)

from .conftest import CLOUD_DEVICE

WATER_HEATER = "water_heater.nimbus"


async def test_water_heater_state_comes_from_device(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the operation modes and temperatures come from the device."""
    state = hass.states.get(WATER_HEATER)

    assert state.state == "Time based"
    assert state.attributes[ATTR_OPERATION_MODE] == "Time based"
    assert state.attributes[ATTR_OPERATION_LIST] == ["Time based", "Always active"]
    assert state.attributes[ATTR_TEMPERATURE] == 50.0
    # 47.5 rounded to the 0 decimals the device sends.
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 48
    assert state.attributes[ATTR_MIN_TEMP] == 40.0
    assert state.attributes[ATTR_MAX_TEMP] == 65.0
    assert state.attributes[ATTR_TARGET_TEMP_STEP] == 1.0


@pytest.mark.parametrize(
    ("mode_changeable", "expected_features"),
    [
        (
            True,
            WaterHeaterEntityFeature.TARGET_TEMPERATURE
            | WaterHeaterEntityFeature.OPERATION_MODE,
        ),
        (False, WaterHeaterEntityFeature.TARGET_TEMPERATURE),
    ],
    ids=["mode-changeable", "mode-fixed"],
)
async def test_water_heater_features_follow_dhw_mode(
    hass: HomeAssistant,
    features: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    mode_changeable: bool,
    expected_features: WaterHeaterEntityFeature,
) -> None:
    """Test the operation mode is offered only when the device can change it."""
    features["dhwModeChangeable"] = mode_changeable
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(WATER_HEATER)
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == expected_features


async def test_water_heater_set_temperature_calls_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device: AristonGalevoDevice,
) -> None:
    """Test the target temperature goes to the device."""
    device.async_set_water_heater_temperature = AsyncMock()

    await hass.services.async_call(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: WATER_HEATER, ATTR_TEMPERATURE: 55},
        blocking=True,
    )

    device.async_set_water_heater_temperature.assert_awaited_once_with(55)


async def test_water_heater_set_temperature_without_temperature_raises(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test a call without a temperature fails.

    The service always sends one, so the entity is called directly.
    """
    entity = hass.data[DATA_COMPONENT].get_entity(WATER_HEATER)

    with pytest.raises(ServiceValidationError) as exc_info:
        await entity.async_set_temperature()

    assert exc_info.value.translation_key == "missing_temperature"


async def test_water_heater_set_operation_mode_calls_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device: AristonGalevoDevice,
) -> None:
    """Test the operation mode text goes to the device."""
    device.async_set_water_heater_operation_mode = AsyncMock()

    await hass.services.async_call(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_OPERATION_MODE,
        {ATTR_ENTITY_ID: WATER_HEATER, ATTR_OPERATION_MODE: "Always active"},
        blocking=True,
    )

    device.async_set_water_heater_operation_mode.assert_awaited_once_with(
        "Always active"
    )


def velis_water_heater(api: MagicMock, power: bool) -> AristonWaterHeater:
    """Return a VELIS water heater built by hand: no fake cloud sets one up."""
    api.async_set_velis_power = AsyncMock()
    device = AristonLydosDevice(api, CLOUD_DEVICE)
    device.data[VelisBaseDeviceProperties.ON] = power
    coordinator = MagicMock(device=device)
    return AristonWaterHeater(coordinator, ARISTON_WATER_HEATER_TYPES[1])


@pytest.mark.parametrize("power", [True, False], ids=["on", "off"])
async def test_water_heater_turn_on_off_sends_power_and_updates(
    api: MagicMock, power: bool
) -> None:
    """Test on and off go to the device and update the entities at once."""
    entity = velis_water_heater(api, not power)

    await (entity.async_turn_on() if power else entity.async_turn_off())

    api.async_set_velis_power.assert_awaited_once()
    assert api.async_set_velis_power.await_args.args[-1] is power
    assert entity.device.water_heater_power_value is power
    entity.coordinator.async_update_listeners.assert_called_once()


@pytest.mark.parametrize("power", [True, False], ids=["on", "off"])
async def test_water_heater_turn_on_off_skips_same_power(
    api: MagicMock, power: bool
) -> None:
    """Test on and off send nothing when the device already has that power."""
    entity = velis_water_heater(api, power)

    await (entity.async_turn_on() if power else entity.async_turn_off())

    api.async_set_velis_power.assert_not_awaited()
    entity.coordinator.async_update_listeners.assert_not_called()
