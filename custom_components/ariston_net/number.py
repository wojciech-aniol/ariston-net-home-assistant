"""Support for Ariston sensors."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import sys
from typing import Any

from ariston_net_api.const import (
    ConsumptionProperties,
    DeviceFeatures,
    EvoOneDeviceProperties,
    MedDeviceSettings,
    NuosSplitProperties,
    SeDeviceSettings,
    SlpDeviceSettings,
    SystemType,
    ThermostatProperties,
    WheType,
)
from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ENERGY_COORDINATOR, NAME
from .coordinator import AristonConfigEntry, DeviceDataUpdateCoordinator
from .entity import (
    AristonBaseEntityDescription,
    AristonEntity,
    cloud_action,
    is_entity_supported,
)

# Send writes to the cloud one at a time.
PARALLEL_UPDATES = 1


@dataclass(kw_only=True, frozen=True)
class AristonNumberEntityDescription(
    NumberEntityDescription, AristonBaseEntityDescription
):
    """A class that describes switch entities."""

    set_native_value: Callable[[Any, float], Coroutine]
    get_native_value: Callable[[Any], Coroutine]
    get_native_min_value: Callable[[Any], float] | None = None
    get_native_max_value: Callable[[Any], float | None] | None = None
    get_native_step: Callable[[Any], Coroutine] | None = None


ARISTON_NUMBER_TYPES: list[AristonNumberEntityDescription] = [
    AristonNumberEntityDescription(
        key=ConsumptionProperties.ELEC_COST,
        name=f"{NAME} elec cost",
        translation_key="elec_cost",
        entity_category=EntityCategory.CONFIG,
        native_min_value=0,
        native_max_value=sys.maxsize,
        native_step=0.01,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: entity.device.elect_cost,
        set_native_value=lambda entity, value: entity.device.async_set_elect_cost(
            value
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key=ConsumptionProperties.GAS_COST,
        name=f"{NAME} gas cost",
        translation_key="gas_cost",
        entity_category=EntityCategory.CONFIG,
        native_min_value=0,
        native_max_value=sys.maxsize,
        native_step=0.01,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: entity.device.gas_cost,
        set_native_value=lambda entity, value: entity.device.async_set_gas_cost(value),
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key=MedDeviceSettings.MED_MAX_SETPOINT_TEMPERATURE,
        name=f"{NAME} max setpoint temperature",
        translation_key="max_setpoint_temperature",
        entity_category=EntityCategory.CONFIG,
        get_native_min_value=lambda entity: (
            entity.device.water_heater_maximum_setpoint_temperature_minimum
        ),
        get_native_max_value=lambda entity: (
            entity.device.water_heater_maximum_setpoint_temperature_maximum
        ),
        native_step=1,
        get_native_value=lambda entity: (
            entity.device.water_heater_maximum_setpoint_temperature
        ),
        set_native_value=lambda entity, value: (
            entity.device.async_set_max_setpoint_temp(value)
        ),
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
    AristonNumberEntityDescription(
        key=SlpDeviceSettings.SLP_MIN_SETPOINT_TEMPERATURE,
        name=f"{NAME} min setpoint temperature",
        translation_key="min_setpoint_temperature",
        entity_category=EntityCategory.CONFIG,
        get_native_min_value=lambda entity: (
            entity.device.water_heater_minimum_setpoint_temperature_minimum
        ),
        get_native_max_value=lambda entity: (
            entity.device.water_heater_minimum_setpoint_temperature_maximum
        ),
        native_step=1,
        get_native_value=lambda entity: (
            entity.device.water_heater_minimum_setpoint_temperature
        ),
        set_native_value=lambda entity, value: (
            entity.device.async_set_min_setpoint_temp(value)
        ),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonNumberEntityDescription(
        key=NuosSplitProperties.REDUCED_TEMP,
        name=f"{NAME} reduced temperature",
        translation_key="reduced_temperature",
        entity_category=EntityCategory.CONFIG,
        get_native_min_value=lambda entity: (
            entity.device.water_heater_minimum_temperature
        ),
        get_native_max_value=lambda entity: (
            entity.device.water_heater_maximum_temperature
        ),
        native_step=1,
        get_native_value=lambda entity: entity.device.water_heater_reduced_temperature,
        set_native_value=lambda entity, value: (
            entity.device.async_set_water_heater_reduced_temperature(value)
        ),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonNumberEntityDescription(
        key=ThermostatProperties.HEATING_FLOW_TEMP,
        name=f"{NAME} heating flow temperature",
        translation_key="heating_flow_temperature",
        entity_category=EntityCategory.CONFIG,
        zone=True,
        get_native_min_value=lambda entity: entity.device.get_heating_flow_temp_min(
            entity.zone
        ),
        get_native_max_value=lambda entity: entity.device.get_heating_flow_temp_max(
            entity.zone
        ),
        get_native_step=lambda entity: entity.device.get_heating_flow_temp_step(
            entity.zone
        ),
        get_native_value=lambda entity: entity.device.get_heating_flow_temp_value(
            entity.zone
        ),
        set_native_value=lambda entity, value: (
            entity.device.async_set_heating_flow_temp(value, entity.zone)
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key=ThermostatProperties.HEATING_FLOW_OFFSET,
        name=f"{NAME} heating flow offset",
        translation_key="heating_flow_offset",
        entity_category=EntityCategory.CONFIG,
        zone=True,
        get_native_min_value=lambda entity: entity.device.get_heating_flow_offset_min(
            entity.zone
        ),
        get_native_max_value=lambda entity: entity.device.get_heating_flow_offset_max(
            entity.zone
        ),
        get_native_step=lambda entity: entity.device.get_heating_flow_offset_step(
            entity.zone
        ),
        get_native_value=lambda entity: entity.device.get_heating_flow_offset_value(
            entity.zone
        ),
        set_native_value=lambda entity, value: (
            entity.device.async_set_heating_flow_offset(value, entity.zone)
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonNumberEntityDescription(
        key=EvoOneDeviceProperties.AV_SHW,
        name=f"{NAME} requested number of showers",
        translation_key="requested_number_of_showers",
        native_min_value=0,
        get_native_max_value=lambda entity: entity.device.max_req_shower,
        native_step=1,
        get_native_value=lambda entity: entity.device.req_shower,
        set_native_value=lambda entity, value: (
            entity.device.async_set_water_heater_number_of_showers(int(value))
        ),
        whe_types=[WheType.Evo],
    ),
    AristonNumberEntityDescription(
        key=SeDeviceSettings.SE_ANTI_COOLING_TEMPERATURE,
        name=f"{NAME} anti cooling temperature",
        translation_key="anti_cooling_temperature",
        entity_category=EntityCategory.CONFIG,
        get_native_min_value=lambda entity: (
            entity.device.anti_cooling_temperature_minimum
        ),
        get_native_max_value=lambda entity: (
            entity.device.anti_cooling_temperature_maximum
        ),
        native_step=1,
        get_native_value=lambda entity: entity.device.anti_cooling_temperature_value,
        set_native_value=lambda entity, value: (
            entity.device.async_set_cooling_temperature_value(int(value))
        ),
        whe_types=[WheType.LydosHybrid],
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Ariston numbers from config entry."""
    ariston_numbers: list[AristonNumber] = []

    for description in ARISTON_NUMBER_TYPES:
        coordinator = entry.runtime_data.get_coordinator(description.coordinator)
        if is_entity_supported(coordinator, description):
            if description.zone:
                for zone_number in coordinator.device.zone_numbers:
                    ariston_numbers.append(
                        AristonNumber(
                            coordinator,
                            description,
                            zone_number,
                        )
                    )
            else:
                ariston_numbers.append(AristonNumber(coordinator, description))

    async_add_entities(ariston_numbers)


class AristonNumber(AristonEntity, NumberEntity):
    """Base class for specific ariston numbers."""

    entity_description: AristonNumberEntityDescription

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonNumberEntityDescription,
        zone: int = 0,
    ) -> None:
        """Initialize the entity."""
        if description.zone:
            self._attr_translation_placeholders = {"zone": str(zone)}
        super().__init__(
            coordinator,
            description,
            zone,
            f"{description.name} {zone}" if zone else None,
        )

    @property
    def native_value(self):
        """Return the current value."""
        return self.entity_description.get_native_value(self)

    @property
    def native_min_value(self):
        """Return the minimum value."""
        if self.entity_description.get_native_min_value is not None:
            return self.entity_description.get_native_min_value(self)

        return self.entity_description.native_min_value

    @property
    def native_max_value(self):
        """Return the maximum value."""
        if self.entity_description.get_native_max_value is not None:
            return self.entity_description.get_native_max_value(self)

        return self.entity_description.native_max_value

    @property
    def native_step(self):
        """Return the step value."""
        if self.entity_description.get_native_step is not None:
            return self.entity_description.get_native_step(self)

        return self.entity_description.native_step

    @cloud_action
    async def async_set_native_value(self, value: float):
        """Update the current value."""
        if value == self.native_value:
            return
        await self.entity_description.set_native_value(self, value)
        self.async_write_ha_state()
