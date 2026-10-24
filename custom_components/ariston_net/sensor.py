"""Support for Ariston sensors."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import (
    ARISTON_SENSOR_TYPES,
    ENERGY_COORDINATOR,
    AristonSensorEntityDescription,
)
from .coordinator import DeviceDataUpdateCoordinator
from .entity import AristonEntity, is_entity_supported

# The library uses this reset time until the energy data changes once.
UNKNOWN_RESET = datetime.fromtimestamp(0, UTC)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston sensors from config entry."""
    data = entry.runtime_data
    ariston_sensors: list[AristonSensor] = []
    skipped_energy_descriptions: list[AristonSensorEntityDescription] = []

    for description in ARISTON_SENSOR_TYPES:
        coordinator = data.get_coordinator(description.coordinator)
        if is_entity_supported(coordinator, description):
            ariston_sensors.append(
                AristonSensor(
                    coordinator,
                    description,
                )
            )
        elif description.coordinator == ENERGY_COORDINATOR:
            skipped_energy_descriptions.append(description)

    async_add_entities(ariston_sensors)

    energy_coordinator = data.energy_coordinator
    if not energy_coordinator or energy_coordinator.last_update_success:
        return

    # Energy features are known only after the first good energy update.
    @callback
    def async_add_energy_sensors() -> None:
        """Add the energy sensors once energy data is available."""
        if (
            not energy_coordinator.last_update_success
            or not skipped_energy_descriptions
        ):
            return
        async_add_entities(
            AristonSensor(energy_coordinator, description)
            for description in skipped_energy_descriptions
            if is_entity_supported(energy_coordinator, description)
        )
        skipped_energy_descriptions.clear()

    entry.async_on_unload(
        energy_coordinator.async_add_listener(async_add_energy_sensors)
    )


class AristonSensor(AristonEntity, SensorEntity):
    """Base class for specific ariston sensors."""

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonSensorEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description)

    @property
    def native_value(self):
        """Return value of sensor."""
        # Without a real reset time, statistics count the value again after a restart.
        if (
            self.entity_description.get_last_reset is not None
            and self.last_reset is None
        ):
            return None
        return self.entity_description.get_native_value(self)

    @property
    def native_unit_of_measurement(self):
        """Return the native unit of measurement."""
        if self.entity_description.get_native_unit_of_measurement is not None:
            return self.entity_description.get_native_unit_of_measurement(self)

        if self.entity_description.native_unit_of_measurement is not None:
            return self.entity_description.native_unit_of_measurement

        return None

    @property
    def last_reset(self) -> datetime | None:
        """Return the time when the sensor was last reset, if any."""
        if self.entity_description.get_last_reset is not None:
            last_reset = self.entity_description.get_last_reset(self)
            if last_reset != UNKNOWN_RESET:
                return last_reset

        return None
