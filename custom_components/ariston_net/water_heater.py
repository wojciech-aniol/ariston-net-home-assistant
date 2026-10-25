"""Support for Ariston water heaters."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from ariston_net_api.const import CustomDeviceFeatures, SystemType, WheType
from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityDescription,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_TARGET_TEMP_STEP,
    DOMAIN,
    EXTRA_STATE_ATTRIBUTE,
    EXTRA_STATE_DEVICE_METHOD,
)
from .coordinator import AristonConfigEntry, DeviceDataUpdateCoordinator
from .entity import (
    AristonBaseEntityDescription,
    AristonEntity,
    cloud_action,
    is_entity_supported,
)

_LOGGER = logging.getLogger(__name__)


# Send writes to the cloud one at a time.
PARALLEL_UPDATES = 1


@dataclass(kw_only=True, frozen=True)
class AristonWaterHeaterEntityDescription(
    WaterHeaterEntityDescription, AristonBaseEntityDescription
):
    """A class that describes water heater entities."""


ARISTON_WATER_HEATER_TYPES: list[AristonWaterHeaterEntityDescription] = [
    AristonWaterHeaterEntityDescription(
        key="AristonWaterHeater",
        translation_key="water_heater",
        extra_states=[
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_TARGET_TEMP_STEP,
                EXTRA_STATE_DEVICE_METHOD: lambda entity: (
                    entity.device.water_heater_temperature_step
                ),
            }
        ],
        device_features=[CustomDeviceFeatures.HAS_DHW],
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
    AristonWaterHeaterEntityDescription(
        key="AristonWaterHeater",
        translation_key="water_heater",
        extra_states=[
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_TARGET_TEMP_STEP,
                EXTRA_STATE_DEVICE_METHOD: lambda entity: (
                    entity.device.water_heater_temperature_step
                ),
            }
        ],
        device_features=[CustomDeviceFeatures.HAS_DHW],
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Andris2,
            WheType.Evo2,
            WheType.Lux,
            WheType.Lux2,
            WheType.Lydos,
            WheType.LydosHybrid,
            WheType.NuosSplit,
        ],
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Ariston water heater device from config entry."""
    ariston_water_heaters: list[AristonWaterHeater] = []
    for description in ARISTON_WATER_HEATER_TYPES:
        coordinator = entry.runtime_data.get_coordinator(description.coordinator)

        if is_entity_supported(coordinator, description):
            ariston_water_heaters.append(AristonWaterHeater(coordinator, description))

    async_add_entities(ariston_water_heaters)


class AristonWaterHeater(AristonEntity, WaterHeaterEntity):
    """Ariston Water Heater Device."""

    _attr_name = None
    entity_description: AristonWaterHeaterEntityDescription

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonWaterHeaterEntityDescription,
    ) -> None:
        """Initialize the water heater."""
        super().__init__(coordinator, description)
        self._attr_unique_id = f"{self.device.gateway}-water_heater"

    @property
    def current_temperature(self):
        """Return the temperature."""
        return self.device.water_heater_current_temperature

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self.device.water_heater_minimum_temperature

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.device.water_heater_target_temperature

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.device.water_heater_maximum_temperature

    @property
    def precision(self) -> float:
        """Return the precision of temperature for the device."""
        return 1 / 10**self.device.water_heater_temperature_decimals

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self.device.water_heater_temperature_unit

    @property
    def supported_features(self) -> int:
        """Return the supported features for this device integration."""
        features = WaterHeaterEntityFeature.TARGET_TEMPERATURE
        if self.device.dhw_mode_changeable:
            features |= WaterHeaterEntityFeature.OPERATION_MODE
        if self.device.system_type == SystemType.VELIS:
            features |= WaterHeaterEntityFeature.ON_OFF
        return features

    @property
    def operation_list(self):
        """List of available operation modes."""
        return self.device.water_heater_mode_operation_texts

    @property
    def current_operation(self):
        """Return current operation."""
        return self.device.water_heater_current_mode_text

    @cloud_action
    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="missing_temperature"
            )

        temperature = kwargs[ATTR_TEMPERATURE]
        _LOGGER.debug(
            "Setting temperature to %d for %s",
            temperature,
            self.entity_id,
        )

        if temperature == self.target_temperature:
            return
        await self.device.async_set_water_heater_temperature(temperature)
        self.async_write_ha_state()

    @cloud_action
    async def async_set_operation_mode(self, operation_mode):
        """Set operation mode."""
        if operation_mode == self.current_operation:
            return
        await self.device.async_set_water_heater_operation_mode(operation_mode)
        self.async_write_ha_state()

    @cloud_action
    async def async_turn_off(self, **kwargs) -> None:
        """Turn the water heater off."""
        await self._async_set_power(False)

    @cloud_action
    async def async_turn_on(self, **kwargs) -> None:
        """Turn the water heater on."""
        await self._async_set_power(True)

    async def _async_set_power(self, power: bool) -> None:
        """Send the power to the device, unless it already has it."""
        if self.device.water_heater_power_value == power:
            return
        await self.device.async_set_power(power)
        # The VELIS power switch shows the same value.
        self.coordinator.async_update_listeners()
