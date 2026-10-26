"""Coordinator class for Ariston module."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from ariston_net_api.ariston_api import ConnectionException
from ariston_net_api.base_device import AristonBaseDevice
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    BUS_ERRORS_COORDINATOR,
    BUS_ERRORS_SCAN_INTERVAL,
    COORDINATOR,
    DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    ENERGY_COORDINATOR,
    ENERGY_SCAN_INTERVAL,
    MAX_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    MAX_ENERGY_SCAN_INTERVAL_MINUTES,
    MAX_SCAN_INTERVAL_SECONDS,
    METERING_COORDINATOR,
    MIN_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    MIN_ENERGY_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_SECONDS,
)
from .errors import CloudErrorKind, classify_error, describe_error

_LOGGER = logging.getLogger(__name__)

MAX_BACKOFF_FACTOR = 8

# Default, minimum and maximum of each interval option.
INTERVAL_OPTIONS: dict[str, tuple[int, int, int]] = {
    CONF_SCAN_INTERVAL: (
        DEFAULT_SCAN_INTERVAL_SECONDS,
        MIN_SCAN_INTERVAL_SECONDS,
        MAX_SCAN_INTERVAL_SECONDS,
    ),
    ENERGY_SCAN_INTERVAL: (
        DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES,
        MIN_ENERGY_SCAN_INTERVAL_MINUTES,
        MAX_ENERGY_SCAN_INTERVAL_MINUTES,
    ),
    BUS_ERRORS_SCAN_INTERVAL: (
        DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
        MIN_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
        MAX_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    ),
}


def interval_option(options: Mapping[str, Any], key: str) -> int:
    """Return an interval option, within its limits.

    Entries saved before the limits may hold a value out of them.
    """
    default, minimum, maximum = INTERVAL_OPTIONS[key]
    return min(max(options.get(key, default), minimum), maximum)


class DeviceDataUpdateCoordinator(DataUpdateCoordinator[None]):
    """Manages polling for state changes from the device."""

    config_entry: AristonConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: AristonConfigEntry,
        device: AristonBaseDevice,
        scan_interval_seconds: int,
        coordinator_name: str,
        async_update_state: Callable[[], Awaitable[Any]],
    ) -> None:
        """Initialize the data update coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}-{device.name}-{coordinator_name}",
            update_interval=timedelta(seconds=scan_interval_seconds),
        )

        self.device = device
        self._async_update_state = async_update_state
        self._default_update_interval = timedelta(seconds=scan_interval_seconds)
        self._backoff_factor = 1
        # Start of the last good update.
        self.data_requested_at: datetime | None = None

    async def _async_update_data(self) -> None:
        """Update the device and poll less often while the cloud rate limits us."""
        requested_at = dt_util.utcnow()
        try:
            await self._async_update_state()
        except ConnectionException as error:
            kind = classify_error(error)
            placeholders = {"error": describe_error(error)}
            if kind is CloudErrorKind.AUTH:
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN,
                    translation_key="auth_failed",
                    translation_placeholders=placeholders,
                ) from error
            if kind is CloudErrorKind.RATE_LIMIT:
                self._backoff_factor = min(self._backoff_factor * 2, MAX_BACKOFF_FACTOR)
                self.update_interval = (
                    self._default_update_interval * self._backoff_factor
                )
                _LOGGER.warning(
                    "Rate limited (429) by Ariston cloud. Next update of %s in %s",
                    self.name,
                    self.update_interval,
                )
                raise UpdateFailed(
                    translation_domain=DOMAIN,
                    translation_key="rate_limited",
                ) from error
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders=placeholders,
            ) from error

        self.data_requested_at = requested_at
        if self._backoff_factor > 1:
            self._backoff_factor = 1
            self.update_interval = self._default_update_interval
            _LOGGER.info(
                "Ariston cloud no longer rate limits %s. Update interval restored",
                self.name,
            )


@dataclass
class AristonData:
    """Coordinators of one config entry. A disabled one is None."""

    coordinator: DeviceDataUpdateCoordinator
    bus_errors_coordinator: DeviceDataUpdateCoordinator | None = None
    energy_coordinator: DeviceDataUpdateCoordinator | None = None
    metering_coordinator: DeviceDataUpdateCoordinator | None = None

    @property
    def coordinators(self) -> dict[str, DeviceDataUpdateCoordinator | None]:
        """Return every coordinator by its name, None when disabled."""
        return {
            COORDINATOR: self.coordinator,
            BUS_ERRORS_COORDINATOR: self.bus_errors_coordinator,
            ENERGY_COORDINATOR: self.energy_coordinator,
            METERING_COORDINATOR: self.metering_coordinator,
        }

    def get_coordinator(self, name: str) -> DeviceDataUpdateCoordinator | None:
        """Return a coordinator by its name, for example a description's one."""
        return self.coordinators[name]


type AristonConfigEntry = ConfigEntry[AristonData]
