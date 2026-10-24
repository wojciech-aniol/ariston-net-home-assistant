"""Coordinator class for Ariston module."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from ariston.ariston_api import ConnectionException
from ariston.base_device import AristonBaseDevice
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BUS_ERRORS_COORDINATOR, COORDINATOR, DOMAIN, ENERGY_COORDINATOR

_LOGGER = logging.getLogger(__name__)

HTTP_TOO_MANY_REQUESTS = 429
MAX_BACKOFF_FACTOR = 8


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

    async def _async_update_data(self) -> None:
        """Update the device and poll less often while the cloud rate limits us."""
        try:
            await self._async_update_state()
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


@dataclass
class AristonData:
    """Coordinators of one config entry. A disabled one is None."""

    coordinator: DeviceDataUpdateCoordinator
    bus_errors_coordinator: DeviceDataUpdateCoordinator | None = None
    energy_coordinator: DeviceDataUpdateCoordinator | None = None

    @property
    def coordinators(self) -> dict[str, DeviceDataUpdateCoordinator | None]:
        """Return every coordinator by its name, None when disabled."""
        return {
            COORDINATOR: self.coordinator,
            BUS_ERRORS_COORDINATOR: self.bus_errors_coordinator,
            ENERGY_COORDINATOR: self.energy_coordinator,
        }

    def get_coordinator(self, name: str) -> DeviceDataUpdateCoordinator | None:
        """Return a coordinator by its name, for example a description's one."""
        return self.coordinators[name]


type AristonConfigEntry = ConfigEntry[AristonData]
