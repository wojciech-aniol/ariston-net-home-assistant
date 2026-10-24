"""Support for Ariston switches."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from ariston_net_api.const import (
    DeviceFeatures,
    DeviceProperties,
    EvoDeviceProperties,
    MedDeviceSettings,
    NuosSplitProperties,
    SeDeviceSettings,
    SlpDeviceSettings,
    SystemType,
    VelisDeviceProperties,
    WheType,
)
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import NAME
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
class AristonSwitchEntityDescription(
    SwitchEntityDescription, AristonBaseEntityDescription
):
    """A class that describes switch entities."""

    set_value: Callable[[Any, bool], Coroutine]
    get_is_on: Callable[[Any], bool]


ARISTON_SWITCH_TYPES: list[AristonSwitchEntityDescription] = [
    AristonSwitchEntityDescription(
        key=DeviceProperties.AUTOMATIC_THERMOREGULATION,
        name=f"{NAME} automatic thermoregulation",
        icon="mdi:radiator",
        device_features=[DeviceFeatures.AUTO_THERMO_REG],
        set_value=lambda entity, value: (
            entity.device.async_set_automatic_thermoregulation(value)
        ),
        get_is_on=lambda entity: entity.device.automatic_thermoregulation,
        system_types=[SystemType.GALEVO],
    ),
    AristonSwitchEntityDescription(
        key=DeviceProperties.IS_QUIET,
        name=f"{NAME} is quiet",
        icon="mdi:volume-off",
        entity_category=EntityCategory.CONFIG,
        device_features=[DeviceProperties.IS_QUIET],
        set_value=lambda entity, value: entity.device.async_set_is_quiet(value),
        get_is_on=lambda entity: entity.device.is_quiet_value,
        system_types=[SystemType.GALEVO],
    ),
    AristonSwitchEntityDescription(
        key=EvoDeviceProperties.ECO,
        name=f"{NAME} eco mode",
        icon="mdi:leaf",
        set_value=lambda entity, value: entity.device.async_set_eco_mode(value),
        get_is_on=lambda entity: entity.device.water_heater_eco_value,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Lux,
            WheType.Evo,
            WheType.Evo2,
            WheType.Lydos,
            WheType.Andris2,
            WheType.Lux2,
        ],
    ),
    AristonSwitchEntityDescription(
        key=EvoDeviceProperties.PWR_OPT,
        name=f"{NAME} power option",
        icon="mdi:leaf",
        set_value=lambda entity, value: (
            entity.device.async_set_water_heater_power_option(value)
        ),
        get_is_on=lambda entity: entity.device.water_heater_power_option_value,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.Lux2],
    ),
    AristonSwitchEntityDescription(
        key=VelisDeviceProperties.ON,
        name=f"{NAME} power",
        icon="mdi:power",
        set_value=lambda entity, value: entity.device.async_set_power(value),
        get_is_on=lambda entity: entity.device.water_heater_power_value,
        system_types=[SystemType.VELIS],
    ),
    AristonSwitchEntityDescription(
        key=MedDeviceSettings.MED_ANTILEGIONELLA_ON_OFF,
        name=f"{NAME} anti legionella",
        icon="mdi:bacteria-outline",
        entity_category=EntityCategory.CONFIG,
        set_value=lambda entity, value: entity.device.async_set_antilegionella(value),
        get_is_on=lambda entity: entity.device.water_anti_leg_value,
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
    AristonSwitchEntityDescription(
        key=SlpDeviceSettings.SLP_PRE_HEATING_ON_OFF,
        name=f"{NAME} preheating",
        icon="mdi:heat-wave",
        entity_category=EntityCategory.CONFIG,
        set_value=lambda entity, value: entity.device.async_set_preheating(value),
        get_is_on=lambda entity: entity.device.water_heater_preheating_on_off,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonSwitchEntityDescription(
        key=NuosSplitProperties.BOOST_ON,
        name=f"{NAME} boost",
        icon="mdi:car-turbocharger",
        entity_category=EntityCategory.CONFIG,
        set_value=lambda entity, value: entity.device.async_set_water_heater_boost(
            value
        ),
        get_is_on=lambda entity: entity.device.water_heater_boost,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonSwitchEntityDescription(
        key=SeDeviceSettings.SE_PERMANENT_BOOST_ON_OFF,
        name=f"{NAME} permanent boost",
        icon="mdi:car-turbocharger",
        entity_category=EntityCategory.CONFIG,
        set_value=lambda entity, value: entity.device.async_set_permanent_boost_value(
            value
        ),
        get_is_on=lambda entity: entity.device.permanent_boost_value,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid],
    ),
    AristonSwitchEntityDescription(
        key=SeDeviceSettings.SE_ANTI_COOLING_ON_OFF,
        name=f"{NAME} anti cooling",
        icon="mdi:snowflake-thermometer",
        entity_category=EntityCategory.CONFIG,
        set_value=lambda entity, value: entity.device.async_set_anti_cooling_value(
            value
        ),
        get_is_on=lambda entity: entity.device.anti_cooling_value,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid],
    ),
    AristonSwitchEntityDescription(
        key=SeDeviceSettings.SE_NIGHT_MODE_ON_OFF,
        name=f"{NAME} night mode",
        icon="mdi:weather-night",
        entity_category=EntityCategory.CONFIG,
        set_value=lambda entity, value: entity.device.async_set_night_mode_value(value),
        get_is_on=lambda entity: entity.device.night_mode_value,
        system_types=[SystemType.VELIS],
        whe_types=[WheType.LydosHybrid],
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Ariston switches from config entry."""
    ariston_switches: list[AristonSwitch] = []
    for description in ARISTON_SWITCH_TYPES:
        coordinator = entry.runtime_data.get_coordinator(description.coordinator)
        if is_entity_supported(coordinator, description):
            ariston_switches.append(
                AristonSwitch(
                    coordinator,
                    description,
                )
            )

    async_add_entities(ariston_switches)


class AristonSwitch(AristonEntity, SwitchEntity):
    """Base class for specific ariston switches."""

    entity_description: AristonSwitchEntityDescription

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description)

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self.entity_description.get_is_on(self)

    @cloud_action
    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self._async_set(True)

    @cloud_action
    async def async_turn_off(self, **kwargs) -> None:
        """Turn the device off."""
        await self._async_set(False)

    async def _async_set(self, is_on: bool) -> None:
        """Turn the switch on or off, unless it already is."""
        if self.is_on == is_on:
            return
        await self.entity_description.set_value(self, is_on)
        self.async_write_ha_state()
