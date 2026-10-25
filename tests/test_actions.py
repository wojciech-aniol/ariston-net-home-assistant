"""Tests that each GALEVO switch, number and select calls the right library method."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from ariston_net_api import AristonGalevoDevice
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
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import set_item


@pytest.fixture
async def init_two_zones(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_ariston: MagicMock,
    full_galevo: MagicMock,
    second_zone: int,
) -> MockConfigEntry:
    """Set up the full GALEVO data set with two zones."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def call_and_check(
    hass: HomeAssistant,
    device: AristonGalevoDevice,
    domain: str,
    service: str,
    data: dict[str, Any],
    method: str,
    expected_args: tuple,
) -> None:
    """Call a service and check the one library call it makes."""
    setattr(device, method, AsyncMock())

    await hass.services.async_call(domain, service, data, blocking=True)

    getattr(device, method).assert_awaited_once_with(*expected_args)


@pytest.mark.parametrize(
    ("entity_id", "item_id", "method"),
    [
        (
            "switch.nimbus_automatic_thermoregulation",
            "AutomaticThermoregulation",
            "async_set_automatic_thermoregulation",
        ),
        ("switch.nimbus_quiet_mode", "IsQuite", "async_set_is_quiet"),
    ],
)
@pytest.mark.parametrize(
    ("service", "value"), [(SERVICE_TURN_ON, True), (SERVICE_TURN_OFF, False)]
)
async def test_switch_calls_library(
    hass: HomeAssistant,
    init_two_zones: MockConfigEntry,
    device: AristonGalevoDevice,
    properties: dict[str, Any],
    entity_id: str,
    item_id: str,
    method: str,
    service: str,
    value: bool,
) -> None:
    """Test turning a switch on or off calls its library method."""
    # The device holds the fake cloud's data, so start from the other value.
    set_item(properties, item_id, value=not value)
    await call_and_check(
        hass,
        device,
        SWITCH_DOMAIN,
        service,
        {ATTR_ENTITY_ID: entity_id},
        method,
        (value,),
    )


@pytest.mark.parametrize(
    ("entity_id", "value", "method", "expected_args"),
    [
        ("number.nimbus_electricity_cost", 0.3, "async_set_elect_cost", (0.3,)),
        ("number.nimbus_gas_cost", 0.12, "async_set_gas_cost", (0.12,)),
        (
            "number.nimbus_zone_1_heating_flow_temperature",
            40,
            "async_set_heating_flow_temp",
            (40.0, 1),
        ),
        (
            "number.nimbus_zone_2_heating_flow_temperature",
            41,
            "async_set_heating_flow_temp",
            (41.0, 2),
        ),
        (
            "number.nimbus_zone_1_heating_flow_offset",
            -2,
            "async_set_heating_flow_offset",
            (-2.0, 1),
        ),
        (
            "number.nimbus_zone_2_heating_flow_offset",
            3,
            "async_set_heating_flow_offset",
            (3.0, 2),
        ),
    ],
)
async def test_number_calls_library(
    hass: HomeAssistant,
    init_two_zones: MockConfigEntry,
    device: AristonGalevoDevice,
    entity_id: str,
    value: float,
    method: str,
    expected_args: tuple,
) -> None:
    """Test setting a number calls its library method, with the zone of the entity."""
    await call_and_check(
        hass,
        device,
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
        method,
        expected_args,
    )


@pytest.mark.parametrize(
    ("entity_id", "expected_value"),
    [
        ("number.nimbus_zone_1_heating_flow_temperature", "38.0"),
        ("number.nimbus_zone_2_heating_flow_temperature", "39.0"),
        ("number.nimbus_zone_1_heating_flow_offset", "0.0"),
        ("number.nimbus_zone_2_heating_flow_offset", "1.0"),
    ],
)
async def test_zone_number_shows_its_zone(
    hass: HomeAssistant,
    init_two_zones: MockConfigEntry,
    entity_id: str,
    expected_value: str,
) -> None:
    """Test a zone number reads the value of the zone in its name."""
    assert hass.states.get(entity_id).state == expected_value


@pytest.mark.parametrize(
    ("entity_id", "option", "method"),
    [
        ("select.nimbus_currency", "CHF", "async_set_currency"),
        ("select.nimbus_gas_type", "LPG", "async_set_gas_type"),
        (
            "select.nimbus_gas_energy_unit",
            "THERM",
            "async_set_gas_energy_unit",
        ),
        (
            "select.nimbus_hybrid_mode",
            "Heat pump only",
            "async_set_hybrid_mode",
        ),
        (
            "select.nimbus_buffer_control_mode",
            "Time program",
            "async_set_buffer_control_mode",
        ),
    ],
)
async def test_select_calls_library(
    hass: HomeAssistant,
    init_two_zones: MockConfigEntry,
    device: AristonGalevoDevice,
    entity_id: str,
    option: str,
    method: str,
) -> None:
    """Test selecting an option passes its text to the library method.

    The plant mode select maps texts to values, see test_select.py.
    """
    await call_and_check(
        hass,
        device,
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, ATTR_OPTION: option},
        method,
        (option,),
    )
