"""Services of the Ariston integration."""

from __future__ import annotations

from ariston import SystemType
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
import voluptuous as vol

from .const import DOMAIN
from .coordinator import AristonConfigEntry, DeviceDataUpdateCoordinator

SERVICE_CREATE_VACATION = "create_vacation"
SERVICE_SET_ITEM_BY_ID = "set_item_by_id"

ATTR_END_DATE = "end_date"
ATTR_ITEM_ID = "item_id"
ATTR_ZONE = "zone"
ATTR_VALUE = "value"

CREATE_VACATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_END_DATE): cv.date,
    }
)

SET_ITEM_BY_ID_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_ITEM_ID): cv.string,
        vol.Required(ATTR_ZONE): cv.positive_int,
        vol.Required(ATTR_VALUE): vol.Coerce(float),
    }
)


def _get_galevo_coordinator(
    hass: HomeAssistant, call: ServiceCall
) -> DeviceDataUpdateCoordinator:
    """Return the state coordinator of the GALEVO device the call targets."""
    device_id = call.data[ATTR_DEVICE_ID]
    placeholders = {"device_id": device_id}
    device_entry = dr.async_get(hass).async_get(device_id)
    entry: AristonConfigEntry | None = None
    if device_entry is not None:
        for domain_entry in hass.config_entries.async_entries(DOMAIN):
            if domain_entry.entry_id in device_entry.config_entries:
                entry = domain_entry
                break
    if entry is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders=placeholders,
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders=placeholders,
        )
    coordinator = entry.runtime_data.coordinator
    if coordinator.device.system_type is not SystemType.GALEVO:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_galevo",
            translation_placeholders=placeholders,
        )
    return coordinator


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the services of the integration.

    The library keeps each new value, so the services update the entities
    without a cloud request.
    """

    async def async_create_vacation(call: ServiceCall) -> None:
        """Create a vacation on the target device, or end it without a date."""
        coordinator = _get_galevo_coordinator(hass, call)
        await coordinator.device.async_set_holiday(call.data.get(ATTR_END_DATE))
        coordinator.async_update_listeners()

    async def async_set_item_by_id(call: ServiceCall) -> None:
        """Set a device or zone item on the target device."""
        coordinator = _get_galevo_coordinator(hass, call)
        await coordinator.device.async_set_item_by_id(
            call.data[ATTR_ITEM_ID], call.data[ATTR_VALUE], call.data[ATTR_ZONE]
        )
        coordinator.async_update_listeners()

    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_VACATION,
        async_create_vacation,
        schema=CREATE_VACATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ITEM_BY_ID,
        async_set_item_by_id,
        schema=SET_ITEM_BY_ID_SCHEMA,
    )
