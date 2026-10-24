"""Tests for the Ariston NET services."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from ariston_net_api import AristonGalevoDevice
from ariston_net_api.ariston_api import ConnectionException
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import ATTR_DEVICE_ID, ATTR_TEMPERATURE, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import DOMAIN

from .conftest import GATEWAY, setup_integration, tracebacks

HOLIDAY = "binary_sensor.nimbus_ariston_net_holiday_mode"
WATER_HEATER = "water_heater.nimbus"

SERVICE_API_METHODS = {
    "create_vacation": "async_set_holiday",
    "set_item_by_id": "async_set_property",
}
SERVICE_DATA: dict[str, dict[str, Any]] = {
    "create_vacation": {"end_date": "2026-11-01"},
    "set_item_by_id": {"item_id": "ZoneComfortTemp", "zone": 1, "value": "21.5"},
}


def device_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    """Return the device registry ID of the entry's device."""
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return device.id


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


async def test_set_item_by_id_service_updates_entities(
    hass: HomeAssistant, api: MagicMock, init_integration: MockConfigEntry
) -> None:
    """Test the set item service shows the new value without a new poll."""
    await hass.services.async_call(
        DOMAIN,
        "set_item_by_id",
        {
            ATTR_DEVICE_ID: device_id(hass, init_integration),
            "item_id": "DhwTemp",
            "zone": 0,
            "value": "55",
        },
        blocking=True,
    )

    api.async_set_property.assert_awaited_once()
    assert hass.states.get(WATER_HEATER).attributes[ATTR_TEMPERATURE] == 55.0


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


@pytest.mark.parametrize("device_type", ["bsb"])
@pytest.mark.parametrize("service", SERVICE_DATA)
async def test_service_other_system_raises(
    hass: HomeAssistant,
    api: MagicMock,
    init_integration: MockConfigEntry,
    service: str,
) -> None:
    """Test a BSB device is refused, as the services are GALEVO only."""
    with pytest.raises(ServiceValidationError) as exc_info:
        await call_service(hass, service, device_id(hass, init_integration))

    assert exc_info.value.translation_key == "not_galevo"
    api.async_set_holiday.assert_not_called()
    api.async_set_property.assert_not_called()


@pytest.mark.parametrize("service", SERVICE_DATA)
async def test_service_cloud_error_raises_ha_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    api: MagicMock,
    caplog: pytest.LogCaptureFixture,
    service: str,
) -> None:
    """Test a cloud error becomes a translated error, without a traceback."""
    getattr(api, SERVICE_API_METHODS[service]).side_effect = ConnectionException(500)

    with pytest.raises(HomeAssistantError) as exc_info:
        await call_service(hass, service, device_id(hass, init_integration))

    assert not isinstance(exc_info.value, ServiceValidationError)
    assert exc_info.value.translation_key == "action_failed"
    assert tracebacks(caplog) == []


async def test_service_auth_error_starts_reauth(
    hass: HomeAssistant, init_integration: MockConfigEntry, api: MagicMock
) -> None:
    """Test a refused login during a service asks for a new password at once."""
    api.async_set_holiday.side_effect = ConnectionException("Invalid token")

    with pytest.raises(HomeAssistantError) as exc_info:
        await call_service(hass, "create_vacation", device_id(hass, init_integration))
    await hass.async_block_till_done()

    assert exc_info.value.translation_key == "action_auth_failed"
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
