"""Tests for which entities Ariston NET creates and their shared parts."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from ariston import AristonGalevoDevice
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import EXTRA_STATE_ATTRIBUTE
from custom_components.ariston_net.sensor import (
    AristonSensor,
    AristonSensorEntityDescription,
)

from .conftest import runtime_data

FLAME = "binary_sensor.nimbus_ariston_net_is_flame_on"
CH_RETURN_TEMP = "sensor.nimbus_ariston_net_ch_return_temp"


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(("has_flame", "expected"), [(True, True), (False, False)])
async def test_flame_sensor_needs_flame_value(
    hass: HomeAssistant,
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    has_flame: bool,
    expected: bool,
) -> None:
    """Test the flame sensor is skipped when the device has no flame value."""
    if not has_flame:
        properties["items"] = [
            item for item in properties["items"] if item["id"] != "IsFlameOn"
        ]

    await setup_integration(hass, config_entry)

    assert (hass.states.get(FLAME) is not None) is expected


@pytest.mark.parametrize(
    ("menu_items", "expected"),
    [([{"id": 124, "value": 31.5, "unit": "°C"}], True), ([], False)],
)
async def test_ch_return_temp_needs_menu_value(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    menu_items: list[dict[str, Any]],
    expected: bool,
) -> None:
    """Test the CH return temperature is skipped without a menu value."""
    api.menu_items_request.return_value = menu_items

    await setup_integration(hass, config_entry)

    state = hass.states.get(CH_RETURN_TEMP)
    assert (state is not None) is expected
    if expected:
        assert state.state == "31.5"


@pytest.mark.parametrize(
    ("whe_type", "whe_model_type", "expected_model"),
    [
        (None, None, "GALEVO"),
        (1, None, "GALEVO Evo"),
        (1, 3, "GALEVO Evo | Model 3"),
    ],
    ids=["no-whe-type", "whe-type", "whe-model"],
)
async def test_device_model_shows_whe_type(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    whe_type: int | None,
    whe_model_type: int | None,
    expected_model: str,
) -> None:
    """Test the device model adds the WHE type and model number when known."""
    if whe_type is not None:
        device.attributes["wheType"] = whe_type
    if whe_model_type is not None:
        device.attributes["wheModelType"] = whe_model_type

    await setup_integration(hass, config_entry)

    (device_entry,) = dr.async_entries_for_config_entry(
        device_registry, config_entry.entry_id
    )
    assert device_entry.model == expected_model


async def test_extra_state_without_method_is_skipped(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test an extra state with no device method adds no attribute.

    No description has one today, so the entity is built directly.
    """
    coordinator = runtime_data(hass).coordinator
    description = AristonSensorEntityDescription(
        key="no_method",
        get_native_value=lambda entity: 1,
        extra_states=[{EXTRA_STATE_ATTRIBUTE: "no_method"}],
    )

    sensor = AristonSensor(coordinator, description)

    assert sensor.extra_state_attributes == {}
