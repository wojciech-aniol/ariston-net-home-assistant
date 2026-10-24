"""The Ariston integration."""

from __future__ import annotations

import logging

from ariston import Ariston, DeviceAttribute, SystemType
from ariston.ariston_api import ConnectionException
from ariston.const import ARISTON_API_URL, ARISTON_USER_AGENT
from homeassistant.const import (
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.unit_system import METRIC_SYSTEM

from .const import (
    API_URL_SETTING,
    API_USER_AGENT,
    BUS_ERRORS_COORDINATOR,
    BUS_ERRORS_SCAN_INTERVAL,
    COORDINATOR,
    DOMAIN,
    ENABLE_BUS_ERRORS,
    ENABLE_ENERGY,
    ENERGY_COORDINATOR,
    ENERGY_SCAN_INTERVAL,
)
from .coordinator import (
    AristonConfigEntry,
    AristonData,
    DeviceDataUpdateCoordinator,
    interval_option,
)
from .errors import CLOUD_ERRORS, CloudErrorKind, classify_error, describe_error
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
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
                translation_placeholders={"error": "login refused"},
            )

        device = await ariston.async_hello(
            entry.data[CONF_DEVICE].get(DeviceAttribute.GW),
            hass.config.units is METRIC_SYSTEM,
        )
        if device is None:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN,
                translation_key="device_not_in_account",
                translation_placeholders={
                    "name": entry.data[CONF_DEVICE].get(DeviceAttribute.NAME) or ""
                },
            )

        if device.system_type is SystemType.GALEVO:
            add_extra_menu_items(
                device.api,
                api_url_setting,
                await async_find_blocked_menu_items(
                    device.api, api_url_setting, device.gw
                ),
            )

        await device.async_get_features()

        scan_interval_seconds = interval_option(entry.options, CONF_SCAN_INTERVAL)
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
            bus_errors_scan_interval_seconds = interval_option(
                entry.options, BUS_ERRORS_SCAN_INTERVAL
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
            energy_interval_minutes = interval_option(
                entry.options, ENERGY_SCAN_INTERVAL
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
    except (ConfigEntryAuthFailed, ConfigEntryNotReady):
        raise
    except CLOUD_ERRORS as error:
        raise _setup_error(error) from error
    except Exception as error:
        _LOGGER.exception("Unexpected error while setting up Ariston NET")
        raise ConfigEntryNotReady from error

    return True


def _setup_error(error: Exception) -> HomeAssistantError:
    """Return the setup error for a cloud error: reauth or a retry later."""
    placeholders = {"error": describe_error(error)}
    if (
        isinstance(error, ConnectionException)
        and classify_error(error) is CloudErrorKind.AUTH
    ):
        return ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="auth_failed",
            translation_placeholders=placeholders,
        )
    return ConfigEntryNotReady(
        translation_domain=DOMAIN,
        translation_key="setup_failed",
        translation_placeholders=placeholders,
    )


async def async_unload_entry(hass: HomeAssistant, entry: AristonConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
