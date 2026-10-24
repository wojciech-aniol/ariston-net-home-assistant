"""The Ariston integration."""

from __future__ import annotations

import logging

from ariston import Ariston, DeviceAttribute, SystemType
from ariston.const import ARISTON_API_URL, ARISTON_USER_AGENT
from homeassistant.const import (
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.unit_system import METRIC_SYSTEM

from .const import (
    API_URL_SETTING,
    API_USER_AGENT,
    BUS_ERRORS_COORDINATOR,
    BUS_ERRORS_SCAN_INTERVAL,
    COORDINATOR,
    DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    ENABLE_BUS_ERRORS,
    ENABLE_ENERGY,
    ENERGY_COORDINATOR,
    ENERGY_SCAN_INTERVAL,
)
from .coordinator import AristonConfigEntry, AristonData, DeviceDataUpdateCoordinator
from .menu_items import add_extra_menu_items, async_find_blocked_menu_items
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Ariston services."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AristonConfigEntry) -> bool:
    """Set up Ariston from a config entry."""
    ariston = Ariston()
    try:
        api_url_setting = entry.data.get(API_URL_SETTING, ARISTON_API_URL)

        api_user_agent = entry.data.get(API_USER_AGENT, ARISTON_USER_AGENT)

        response = await ariston.async_connect(
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            api_url_setting,
            api_user_agent,
        )
        if not response:
            _LOGGER.error(
                "Failed to connect to Ariston with device: %s",
                entry.data[CONF_DEVICE].get(DeviceAttribute.NAME),
            )
            raise ConfigEntryAuthFailed

        device = await ariston.async_hello(
            entry.data[CONF_DEVICE].get(DeviceAttribute.GW),
            hass.config.units is METRIC_SYSTEM,
        )
        if device is None:
            return False

        if device.system_type is SystemType.GALEVO:
            add_extra_menu_items(
                device.api,
                api_url_setting,
                await async_find_blocked_menu_items(
                    device.api, api_url_setting, device.gw
                ),
            )

        await device.async_get_features()

        scan_interval_seconds = entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS
        )
        coordinator = DeviceDataUpdateCoordinator(
            hass,
            entry,
            device,
            scan_interval_seconds,
            COORDINATOR,
            device.async_update_state,
        )
        await coordinator.async_config_entry_first_refresh()
        data = AristonData(coordinator)

        if entry.options.get(ENABLE_BUS_ERRORS, True):
            bus_errors_scan_interval_seconds = entry.options.get(
                BUS_ERRORS_SCAN_INTERVAL, DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS
            )
            data.bus_errors_coordinator = DeviceDataUpdateCoordinator(
                hass,
                entry,
                device,
                bus_errors_scan_interval_seconds,
                BUS_ERRORS_COORDINATOR,
                device.async_get_bus_errors,
            )
            # Bus errors are optional, like the energy data below.
            try:
                await data.bus_errors_coordinator.async_config_entry_first_refresh()
            except ConfigEntryNotReady as error:
                _LOGGER.warning(
                    "Could not fetch Ariston bus errors, continuing without "
                    "them for now: %s",
                    error,
                )

        if device.has_metering and entry.options.get(ENABLE_ENERGY, True):
            energy_interval_minutes = entry.options.get(
                ENERGY_SCAN_INTERVAL, DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES
            )
            data.energy_coordinator = DeviceDataUpdateCoordinator(
                hass,
                entry,
                device,
                energy_interval_minutes * 60,
                ENERGY_COORDINATOR,
                device.async_update_energy,
            )
            # The energy/consumption endpoint is optional and the Ariston cloud
            # occasionally returns errors (e.g. HTTP 500) for it. Don't let that
            # failure tear down the whole config entry: log it and continue so the
            # climate, water heater and status entities still load. The energy
            # sensors will populate on a later successful refresh.
            try:
                await data.energy_coordinator.async_config_entry_first_refresh()
            except ConfigEntryNotReady as error:
                _LOGGER.warning(
                    "Could not fetch Ariston energy data, continuing without "
                    "energy sensors for now: %s",
                    error,
                )

        entry.runtime_data = data
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        entry.async_on_unload(entry.add_update_listener(update_listener))
    except ConfigEntryAuthFailed:
        raise
    except Exception as error:
        _LOGGER.exception("Failed to set up Ariston NET")
        raise ConfigEntryNotReady from error

    return True


async def update_listener(hass: HomeAssistant, entry: AristonConfigEntry) -> None:
    """Update listener."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AristonConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
