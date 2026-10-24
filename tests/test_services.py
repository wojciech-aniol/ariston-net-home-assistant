"""Tests for the Ariston NET services."""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from ariston import AristonBsbDevice, AristonGalevoDevice
from homeassistant.const import ATTR_DEVICE_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import DOMAIN

from .conftest import CLOUD_DEVICE, GATEWAY

HOLIDAY = "binary_sensor.nimbus_ariston_net_holiday_mode"

SERVICE_DATA: dict[str, dict[str, Any]] = {
    "create_vacation": {"end_date": "2026-11-01"},
    "set_item_by_id": {"item_id": "ZoneComfortTemp", "zone": 1, "value": "21.5"},
}


def device_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Return the device registry ID of the entry's device."""
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return device.id


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def call_service(hass: HomeAssistant, service: str, target: str) -> None:
    """Call a service with valid data for the target device."""
    await hass.services.async_call(
        DOMAIN,
        service,
        {ATTR_DEVICE_ID: target} | SERVICE_DATA[service],
        blocking=True,
    )


async def test_set_item_by_id_service_calls_device(
    hass: HomeAssistant,
    device: AristonGalevoDevice,
    init_integration: MockConfigEntry,
) -> None:
    """Test the set item service passes the item, value and zone on."""
    device.async_set_item_by_id = AsyncMock()

    await call_service(hass, "set_item_by_id", device_id(hass, init_integration))

    device.async_set_item_by_id.assert_awaited_once_with("ZoneComfortTemp", 21.5, 1)


async def test_create_vacation_service_sets_end_date(
    hass: HomeAssistant, api: MagicMock, init_integration: MockConfigEntry
) -> None:
    """Test the vacation service sends the end date and turns holiday on."""
    await call_service(hass, "create_vacation", device_id(hass, init_integration))

    api.async_set_holiday.assert_awaited_once_with(GATEWAY, "2026-11-01T00:00:00")
    state = hass.states.get(HOLIDAY)
    assert state.state == STATE_ON
    assert state.attributes["holiday"] == "2026-11-01T00:00:00"


async def test_create_vacation_service_without_date_ends_holiday(
    hass: HomeAssistant,
    api: MagicMock,
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test the vacation service with no date turns holiday off."""
    holiday = next(item for item in properties["items"] if item["id"] == "Holiday")
    holiday.update(value=True, expiresOn="2026-11-01T00:00:00")
    await setup_integration(hass, config_entry)
    assert hass.states.get(HOLIDAY).state == STATE_ON

    await hass.services.async_call(
        DOMAIN,
        "create_vacation",
        {ATTR_DEVICE_ID: device_id(hass, config_entry)},
        blocking=True,
    )

    api.async_set_holiday.assert_awaited_once_with(GATEWAY, None)
    state = hass.states.get(HOLIDAY)
    assert state.state == STATE_OFF
    assert "holiday" not in state.attributes


@pytest.mark.parametrize("service", SERVICE_DATA)
async def test_service_unknown_device_raises(
    hass: HomeAssistant, init_integration: MockConfigEntry, service: str
) -> None:
    """Test a device ID that is not in the registry is refused."""
    with pytest.raises(ServiceValidationError) as exc_info:
        await call_service(hass, service, "unknown")

    assert exc_info.value.translation_key == "device_not_found"


@pytest.mark.parametrize("service", SERVICE_DATA)
async def test_service_other_integration_device_raises(
    hass: HomeAssistant, init_integration: MockConfigEntry, service: str
) -> None:
    """Test a device of another integration is refused."""
    other_entry = MockConfigEntry(domain="other")
    other_entry.add_to_hass(hass)
    other_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=other_entry.entry_id, identifiers={("other", "1")}
    )

    with pytest.raises(ServiceValidationError) as exc_info:
        await call_service(hass, service, other_device.id)

    assert exc_info.value.translation_key == "device_not_found"


@pytest.mark.parametrize("service", SERVICE_DATA)
async def test_service_unloaded_entry_raises(
    hass: HomeAssistant, init_integration: MockConfigEntry, service: str
) -> None:
    """Test a device whose entry is unloaded is refused."""
    target = device_id(hass, init_integration)
    await hass.config_entries.async_unload(init_integration.entry_id)

    with pytest.raises(ServiceValidationError) as exc_info:
        await call_service(hass, service, target)

    assert exc_info.value.translation_key == "entry_not_loaded"


@pytest.mark.parametrize("service", SERVICE_DATA)
async def test_service_other_system_raises(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    service: str,
) -> None:
    """Test a BSB device is refused, as the services are GALEVO only."""
    api.async_get_bsb_plant_data = AsyncMock(return_value={})
    mock_ariston.async_hello.return_value = AristonBsbDevice(
        api, copy.deepcopy(CLOUD_DEVICE) | {"sys": 5}
    )
    await setup_integration(hass, config_entry)

    with pytest.raises(ServiceValidationError) as exc_info:
        await call_service(hass, service, device_id(hass, config_entry))

    assert exc_info.value.translation_key == "not_galevo"
    api.async_set_holiday.assert_not_called()
