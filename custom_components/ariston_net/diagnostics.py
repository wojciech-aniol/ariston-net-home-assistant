"""Diagnostics support for Ariston NET."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import AristonConfigEntry

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "gw",
    "gwId",
    "sn",
    "serialNumber",
    "lnk",
    "loc",
    "name",
    "geofenceConfig",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AristonConfigEntry
) -> dict[str, Any]:
    """Return the raw cloud data of the device, without personal data."""
    data = entry.runtime_data
    device = data.coordinator.device

    return async_redact_data(
        {
            "entry": {"data": dict(entry.data), "options": dict(entry.options)},
            "device": {
                "system_type": device.system_type.name,
                "whe_type": device.whe_type.name,
                "whe_model_type": device.whe_model_type,
                "firmware_version": device.firmware_version,
                "attributes": device.attributes,
                "features": device.features,
                "custom_features": device.custom_features,
                "data": device.data,
                "menu_items": getattr(device, "menu_items", None),
                "bus_errors": device.bus_errors,
                "consumptions_sequences": device.consumptions_sequences,
            },
            "coordinators": {
                name: {
                    "last_update_success": coordinator.last_update_success,
                    "update_interval": str(coordinator.update_interval),
                }
                for name, coordinator in data.coordinators.items()
                if coordinator
            },
        },
        TO_REDACT,
    )
