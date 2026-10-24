"""Tests that count the requests sent to the Ariston cloud."""

from __future__ import annotations

from collections import Counter
from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
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
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import (
    BUS_ERRORS_COORDINATOR,
    COORDINATOR,
    ENERGY_COORDINATOR,
)

from .conftest import runtime_data

CLIMATE = "climate.nimbus"
WATER_HEATER = "water_heater.nimbus"
PLANT_MODE = "select.nimbus_ariston_net_plant_mode"
CURRENCY = "select.nimbus_ariston_net_currency"
THERMOREGULATION = "switch.nimbus_ariston_net_automatic_thermoregulation"
FLOW_TEMP = "number.nimbus_ariston_net_heating_flow_temperature_1"
ELEC_COST = "number.nimbus_ariston_net_elec_cost"

# Fake routes of _async_get in the api fixture, counted instead of _async_get.
ROUTED = "_async_get"


def cloud_requests(*mocks: MagicMock) -> dict[str, int]:
    """Return how many times each cloud request was sent."""
    return dict(
        Counter(
            name
            for mock in mocks
            for name, _, _ in mock.mock_calls
            if name != ROUTED and "." not in name
        )
    )


async def test_setup_requests(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_ariston: MagicMock,
    full_galevo: MagicMock,
) -> None:
    """Test the requests sent to set the entry up."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert cloud_requests(mock_ariston, full_galevo) == {
        "async_connect": 1,
        "async_hello": 1,
        "blocked_menu_items_request": 1,
        "async_get_features_for_device": 1,
        "async_get_properties": 1,
        "menu_items_request": 1,
        "async_get_bus_errors": 1,
        "async_get_consumptions_sequences": 1,
        "async_get_consumptions_settings": 1,
        "async_get_energy_account": 1,
    }


@pytest.mark.parametrize(
    ("coordinator", "expected"),
    [
        (COORDINATOR, {"async_get_properties": 1, "menu_items_request": 1}),
        (BUS_ERRORS_COORDINATOR, {"async_get_bus_errors": 1}),
        (
            ENERGY_COORDINATOR,
            {
                "async_get_consumptions_sequences": 1,
                "async_get_consumptions_settings": 1,
                "async_get_energy_account": 1,
            },
        ),
    ],
)
async def test_poll_requests(
    hass: HomeAssistant,
    init_full_integration: MockConfigEntry,
    full_galevo: MagicMock,
    coordinator: str,
    expected: dict[str, int],
) -> None:
    """Test the requests of one poll of each coordinator."""
    full_galevo.reset_mock()

    await runtime_data(hass).get_coordinator(coordinator).async_refresh()

    assert cloud_requests(full_galevo) == expected


# Stands for the value the entity shows now.
CURRENT = object()
# Where the state holds that value: an attribute, or None for the state itself.
SHOWN_IN = {
    ATTR_OPTION: None,
    ATTR_VALUE: None,
    ATTR_OPERATION_MODE: ATTR_OPERATION_MODE,
}


def with_current_values(
    hass: HomeAssistant, entity_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Return the data with CURRENT replaced by the value the entity shows."""
    state = hass.states.get(entity_id)
    return {
        key: (
            (state.attributes[SHOWN_IN[key]] if SHOWN_IN[key] else state.state)
            if value is CURRENT
            else value
        )
        for key, value in data.items()
    }


ACTIONS = [
    pytest.param(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        CLIMATE,
        {ATTR_HVAC_MODE: HVACMode.HEAT},
        0,
        id="hvac-mode-same",
    ),
    pytest.param(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        CLIMATE,
        {ATTR_HVAC_MODE: HVACMode.AUTO},
        1,
        id="hvac-mode-auto",
    ),
    pytest.param(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        CLIMATE,
        {ATTR_HVAC_MODE: HVACMode.OFF},
        1,
        id="hvac-mode-off",
    ),
    pytest.param(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        CLIMATE,
        {ATTR_PRESET_MODE: "Winter"},
        2,
        id="preset-same",
    ),
    pytest.param(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        CLIMATE,
        {ATTR_PRESET_MODE: "Summer"},
        3,
        id="preset-summer",
    ),
    pytest.param(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        CLIMATE,
        {ATTR_TEMPERATURE: 22.0},
        0,
        id="climate-temperature-same",
    ),
    pytest.param(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        CLIMATE,
        {ATTR_TEMPERATURE: 23.0},
        1,
        id="climate-temperature-new",
    ),
    pytest.param(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        PLANT_MODE,
        {ATTR_OPTION: CURRENT},
        0,
        id="plant-mode-same",
    ),
    pytest.param(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        PLANT_MODE,
        {ATTR_OPTION: "Summer"},
        1,
        id="plant-mode-summer",
    ),
    pytest.param(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        CURRENCY,
        {ATTR_OPTION: CURRENT},
        0,
        id="currency-same",
    ),
    pytest.param(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        CURRENCY,
        {ATTR_OPTION: "CHF"},
        1,
        id="currency-new",
    ),
    pytest.param(
        SWITCH_DOMAIN, SERVICE_TURN_ON, THERMOREGULATION, {}, 0, id="switch-same"
    ),
    pytest.param(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, THERMOREGULATION, {}, 1, id="switch-off"
    ),
    pytest.param(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        FLOW_TEMP,
        {ATTR_VALUE: CURRENT},
        0,
        id="flow-temp-same",
    ),
    pytest.param(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        FLOW_TEMP,
        {ATTR_VALUE: 40},
        1,
        id="flow-temp-new",
    ),
    pytest.param(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        ELEC_COST,
        {ATTR_VALUE: CURRENT},
        0,
        id="elec-cost-same",
    ),
    pytest.param(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        ELEC_COST,
        {ATTR_VALUE: 0.3},
        1,
        id="elec-cost-new",
    ),
    pytest.param(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        WATER_HEATER,
        {ATTR_TEMPERATURE: 50},
        0,
        id="dhw-temperature-same",
    ),
    pytest.param(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        WATER_HEATER,
        {ATTR_TEMPERATURE: 55},
        1,
        id="dhw-temperature-new",
    ),
    pytest.param(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_OPERATION_MODE,
        WATER_HEATER,
        {ATTR_OPERATION_MODE: CURRENT},
        0,
        id="dhw-mode-same",
    ),
    pytest.param(
        WATER_HEATER_DOMAIN,
        SERVICE_SET_OPERATION_MODE,
        WATER_HEATER,
        {ATTR_OPERATION_MODE: "Always active"},
        1,
        id="dhw-mode-new",
    ),
]


@pytest.mark.parametrize(
    ("domain", "service", "entity_id", "data", "expected"), ACTIONS
)
async def test_action_requests(
    hass: HomeAssistant,
    init_full_integration: MockConfigEntry,
    full_galevo: MagicMock,
    domain: str,
    service: str,
    entity_id: str,
    data: dict[str, Any],
    expected: int,
) -> None:
    """Test how many requests one action sends."""
    data = with_current_values(hass, entity_id, data)
    full_galevo.reset_mock()

    await hass.services.async_call(
        domain, service, {ATTR_ENTITY_ID: entity_id, **data}, blocking=True
    )

    assert sum(cloud_requests(full_galevo).values()) == expected
