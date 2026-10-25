"""Support for Ariston sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ariston_net_api.const import (
    DeviceFeatures,
    DeviceProperties,
    EvoLydosDeviceProperties,
    SystemType,
    WheType,
)
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ATTR_HOLIDAY, EXTRA_STATE_ATTRIBUTE, EXTRA_STATE_DEVICE_METHOD, NAME
from .coordinator import AristonConfigEntry, DeviceDataUpdateCoordinator
from .entity import AristonBaseEntityDescription, AristonEntity, is_entity_supported

PARALLEL_UPDATES = 0


@dataclass(kw_only=True, frozen=True)
class AristonBinarySensorEntityDescription(
    BinarySensorEntityDescription, AristonBaseEntityDescription
):
    """A class that describes binary sensor entities."""

    get_is_on: Callable[[Any], bool]


ARISTON_BINARY_SENSOR_TYPES: list[AristonBinarySensorEntityDescription] = [
    AristonBinarySensorEntityDescription(
        key=DeviceProperties.IS_FLAME_ON,
        name=f"{NAME} is flame on",
        translation_key="is_flame_on",
        get_is_on=lambda entity: entity.device.is_flame_on_value,
        get_is_supported=lambda device: device.is_flame_on_value is not None,
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
    AristonBinarySensorEntityDescription(
        key=DeviceProperties.IS_HEATING_PUMP_ON,
        name=f"{NAME} is heating pump on",
        translation_key="is_heating_pump_on",
        get_is_on=lambda entity: entity.device.is_heating_pump_on_value,
        device_features=[DeviceFeatures.HP_SYS],
        system_types=[SystemType.GALEVO],
    ),
    # BSB has no hpSys feature; gas boilers may send no hpOn.
    AristonBinarySensorEntityDescription(
        key=DeviceProperties.IS_HEATING_PUMP_ON,
        name=f"{NAME} is heating pump on",
        translation_key="is_heating_pump_on",
        get_is_on=lambda entity: entity.device.is_heating_pump_on_value,
        get_is_supported=lambda device: device.is_heating_pump_on_value is not None,
        system_types=[SystemType.BSB],
    ),
    AristonBinarySensorEntityDescription(
        key=DeviceProperties.HOLIDAY,
        name=f"{NAME} holiday mode",
        translation_key="holiday_mode",
        extra_states=[
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_HOLIDAY,
                EXTRA_STATE_DEVICE_METHOD: lambda entity: (
                    entity.device.holiday_expires_on
                ),
            }
        ],
        get_is_on=lambda entity: entity.device.holiday_mode_value,
        system_types=[SystemType.GALEVO],
    ),
    AristonBinarySensorEntityDescription(
        key=EvoLydosDeviceProperties.HEAT_REQ,
        name=f"{NAME} is heating",
        translation_key="is_heating",
        get_is_on=lambda entity: entity.device.is_heating,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Lux,
            WheType.Evo,
            WheType.Evo2,
            WheType.Lydos,
            WheType.LydosHybrid,
            WheType.Andris2,
            WheType.Lux2,
        ],
    ),
    AristonBinarySensorEntityDescription(
        key=EvoLydosDeviceProperties.ANTI_LEG,
        name=f"{NAME} anti-legionella cycle",
        translation_key="anti_legionella_cycle",
        get_is_on=lambda entity: entity.device.is_antileg,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Evo2,
            WheType.Lydos,
            WheType.LydosHybrid,
            WheType.Andris2,
        ],
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Ariston binary sensors from config entry."""
    ariston_binary_sensors: list[AristonBinarySensor] = []
    for description in ARISTON_BINARY_SENSOR_TYPES:
        coordinator = entry.runtime_data.get_coordinator(description.coordinator)
        if is_entity_supported(coordinator, description):
            ariston_binary_sensors.append(AristonBinarySensor(coordinator, description))

    async_add_entities(ariston_binary_sensors)


class AristonBinarySensor(AristonEntity, BinarySensorEntity):
    """Base class for specific ariston binary sensors."""

    entity_description: AristonBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonBinarySensorEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description)

    @property
    def is_on(self):
        """Return True if the binary sensor is on."""
        return self.entity_description.get_is_on(self)
