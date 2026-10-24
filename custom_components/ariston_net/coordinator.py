"""Coordinator class for Ariston module."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
import logging

from ariston.ariston_api import ConnectionException
from ariston.base_device import AristonBaseDevice
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BUS_ERRORS_COORDINATOR, COORDINATOR, DOMAIN, ENERGY_COORDINATOR

_LOGGER = logging.getLogger(__name__)

HTTP_TOO_MANY_REQUESTS = 429
MAX_BACKOFF_FACTOR = 8


class DeviceDataUpdateCoordinator(DataUpdateCoordinator):
    """Manages polling for state changes from the device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: AristonBaseDevice,
        scan_interval_seconds: int,
        coordinator_name: str,
        async_update_state: Callable,
    ) -> None:
        """Initialize the data update coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{device.name}-{coordinator_name}",
            update_interval=timedelta(seconds=scan_interval_seconds),
            update_method=self._async_update_with_backoff,
        )

        self.device = device
        self._async_update_state = async_update_state
        self._default_update_interval = timedelta(seconds=scan_interval_seconds)
        self._backoff_factor = 1

    async def _async_update_with_backoff(self):
        """Update data and poll less often while the cloud rate limits us."""
        try:
            data = await self._async_update_state()
        except ConnectionException as error:
            # The library raises ConnectionException(status, body) on HTTP 429.
            if not error.args or error.args[0] != HTTP_TOO_MANY_REQUESTS:
                raise
            self._backoff_factor = min(self._backoff_factor * 2, MAX_BACKOFF_FACTOR)
            self.update_interval = self._default_update_interval * self._backoff_factor
            _LOGGER.warning(
                "Rate limited (429) by Ariston cloud. Next update of %s in %s",
                self.name,
                self.update_interval,
            )
            raise UpdateFailed("Rate limited (429) by Ariston cloud") from error

        if self._backoff_factor > 1:
            self._backoff_factor = 1
            self.update_interval = self._default_update_interval
            _LOGGER.info(
                "Ariston cloud no longer rate limits %s. Update interval restored",
                self.name,
            )
        return data


@dataclass
class AristonData:
    """Coordinators of one config entry. A disabled one is None."""

    coordinator: DeviceDataUpdateCoordinator
    bus_errors_coordinator: DeviceDataUpdateCoordinator | None = None
    energy_coordinator: DeviceDataUpdateCoordinator | None = None

    def get_coordinator(self, name: str) -> DeviceDataUpdateCoordinator | None:
        """Return a coordinator by its name, for example a description's one."""
        return {
            COORDINATOR: self.coordinator,
            BUS_ERRORS_COORDINATOR: self.bus_errors_coordinator,
            ENERGY_COORDINATOR: self.energy_coordinator,
        }[name]


type AristonConfigEntry = ConfigEntry[AristonData]
