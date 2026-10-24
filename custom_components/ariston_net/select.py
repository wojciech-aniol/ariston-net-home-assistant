"""Support for Ariston sensors."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from ariston.const import (
    ConsumptionProperties,
    DeviceFeatures,
    DeviceProperties,
    EvoOneDeviceProperties,
    PlantMode,
    SystemType,
    WheType,
)
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ENERGY_COORDINATOR, NAME
from .coordinator import AristonConfigEntry, DeviceDataUpdateCoordinator
from .entity import AristonBaseEntityDescription, AristonEntity, is_entity_supported


@dataclass(kw_only=True, frozen=True)
class AristonSelectEntityDescription(
    SelectEntityDescription, AristonBaseEntityDescription
):
    """A class that describes select entities."""

    get_current_option: Callable[[Any], str]
    get_options: Callable[[Any], list[str]]
    select_option: Callable[[Any, str], Coroutine]


async def _async_select_plant_mode(entity, option: str) -> None:
    """Set the plant mode from one of its option texts."""
    device = entity.device
    index = device.plant_mode_opt_texts.index(option)
    await device.async_set_plant_mode(PlantMode(device.plant_mode_options[index]))
    # Climate entities show the plant mode too, so update them now.
    entity.coordinator.async_update_listeners()


ARISTON_SELECT_TYPES: list[AristonSelectEntityDescription] = [
    AristonSelectEntityDescription(
        key=DeviceProperties.PLANT_MODE,
        name=f"{NAME} plant mode",
        icon="mdi:sun-snowflake-variant",
        get_current_option=lambda entity: entity.device.plant_mode_text,
        get_options=lambda entity: entity.device.plant_mode_opt_texts,
        select_option=_async_select_plant_mode,
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=ConsumptionProperties.CURRENCY,
        name=f"{NAME} currency",
        icon="mdi:cash-100",
        device_class=SensorDeviceClass.MONETARY,
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_current_option=lambda entity: entity.device.currency,
        get_options=lambda entity: entity.device.get_currencies(),
        select_option=lambda entity, option: entity.device.async_set_currency(option),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=ConsumptionProperties.GAS_TYPE,
        name=f"{NAME} gas type",
        icon="mdi:gas-cylinder",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_current_option=lambda entity: entity.device.gas_type,
        get_options=lambda entity: entity.device.get_gas_types(),
        select_option=lambda entity, option: entity.device.async_set_gas_type(option),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=ConsumptionProperties.GAS_ENERGY_UNIT,
        name=f"{NAME} gas energy unit",
        icon="mdi:cube-scan",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_current_option=lambda entity: entity.device.gas_energy_unit,
        get_options=lambda entity: entity.device.get_gas_energy_units(),
        select_option=lambda entity, option: entity.device.async_set_gas_energy_unit(
            option
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=DeviceProperties.HYBRID_MODE,
        name=f"{NAME} hybrid mode",
        icon="mdi:cog",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.HYBRID_SYS],
        get_current_option=lambda entity: entity.device.hybrid_mode,
        get_options=lambda entity: entity.device.hybrid_mode_opt_texts,
        select_option=lambda entity, option: entity.device.async_set_hybrid_mode(
            option
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=DeviceProperties.BUFFER_CONTROL_MODE,
        name=f"{NAME} buffer control mode",
        icon="mdi:cup-water",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceFeatures.BUFFER_TIME_PROG_AVAILABLE],
        get_current_option=lambda entity: entity.device.buffer_control_mode,
        get_options=lambda entity: entity.device.buffer_control_mode_opt_texts,
        select_option=lambda entity, option: (
            entity.device.async_set_buffer_control_mode(option)
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSelectEntityDescription(
        key=EvoOneDeviceProperties.MODE,
        name=f"{NAME} operation mode",
        icon="mdi:cog",
        get_current_option=lambda entity: entity.device.water_heater_current_mode_text,
        get_options=lambda entity: entity.device.water_heater_mode_operation_texts,
        select_option=lambda entity, option: (
            entity.device.async_set_water_heater_operation_mode(option)
        ),
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Evo],
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Ariston selects from config entry."""
    ariston_select: list[AristonSelect] = []

    for description in ARISTON_SELECT_TYPES:
        coordinator = entry.runtime_data.get_coordinator(description.coordinator)
        if is_entity_supported(coordinator, description):
            ariston_select.append(
                AristonSelect(
                    coordinator,
                    description,
                )
            )

    async_add_entities(ariston_select)


class AristonSelect(AristonEntity, SelectEntity):
    """Base class for specific ariston selects."""

    entity_description: AristonSelectEntityDescription

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonSelectEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description)

    @property
    def current_option(self):
        """Return current selected option."""
        return self.entity_description.get_current_option(self)

    @property
    def options(self):
        """Return options."""
        return self.entity_description.get_options(self)

    async def async_select_option(self, option: str):
        """Change the selected option."""
        await self.entity_description.select_option(self, option)
        self.async_write_ha_state()
