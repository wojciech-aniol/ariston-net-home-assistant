"""Support for Ariston sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ariston.const import (
    ARISTON_BUS_ERRORS,
    ConsumptionType,
    CustomDeviceFeatures,
    DeviceAttribute,
    DeviceFeatures,
    DeviceProperties,
    EvoDeviceProperties,
    EvoLydosDeviceProperties,
    EvoOneDeviceProperties,
    MenuItemNames,
    PropertyType,
    SlpDeviceSettings,
    SystemType,
    VelisDeviceProperties,
    WheType,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory

from .const import (
    ATTR_ERRORS,
    BUS_ERRORS_COORDINATOR,
    ENERGY_COORDINATOR,
    EXTRA_STATE_ATTRIBUTE,
    EXTRA_STATE_DEVICE_METHOD,
    NAME,
)
from .coordinator import DeviceDataUpdateCoordinator
from .entity import AristonBaseEntityDescription, AristonEntity, is_entity_supported
from .menu_items import ExtraMenuItem, MenuNode, menu_item_value, menu_node_value

# The library uses this reset time until the energy data changes once.
UNKNOWN_RESET = datetime.fromtimestamp(0, UTC)


@dataclass(kw_only=True, frozen=True)
class AristonSensorEntityDescription(
    SensorEntityDescription, AristonBaseEntityDescription
):
    """A class that describes sensor entities."""

    get_native_unit_of_measurement: Callable[[Any], str] | None = None
    get_last_reset: Callable[[Any], datetime] | None = None
    get_native_value: Callable[[Any], Any]


ARISTON_SENSOR_TYPES: list[AristonSensorEntityDescription] = [
    AristonSensorEntityDescription(
        key=DeviceProperties.HEATING_CIRCUIT_PRESSURE,
        name=f"{NAME} heating circuit pressure",
        device_class=SensorDeviceClass.PRESSURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.heating_circuit_pressure_value,
        get_native_unit_of_measurement=lambda entity: (
            entity.device.heating_circuit_pressure_unit
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.CH_FLOW_SETPOINT_TEMP,
        name=f"{NAME} CH flow setpoint temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.ch_flow_setpoint_temp_value,
        get_native_unit_of_measurement=lambda entity: (
            entity.device.ch_flow_setpoint_temp_unit
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.CH_FLOW_TEMP,
        name=f"{NAME} CH flow temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.ch_flow_temp_value,
        get_native_unit_of_measurement=lambda entity: entity.device.ch_flow_temp_unit,
        device_features=[DeviceProperties.CH_FLOW_TEMP],
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=str(MenuItemNames.SIGNAL_STRENGTH),
        name=f"{NAME} signal strength",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        get_native_value=lambda entity: entity.device.signal_strength_value,
        get_native_unit_of_measurement=lambda entity: (
            entity.device.signal_strength_unit
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=str(MenuItemNames.CH_RETURN_TEMP),
        name=f"{NAME} CH return temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.ch_return_temp_value,
        get_native_unit_of_measurement=lambda entity: entity.device.ch_return_temp_unit,
        get_is_supported=lambda device: device.ch_return_temp_value is not None,
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=str(ExtraMenuItem.HP_WATER_FLOW_TEMP),
        name=f"{NAME} HP water flow temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: menu_item_value(
            entity.device, ExtraMenuItem.HP_WATER_FLOW_TEMP
        ),
        get_native_unit_of_measurement=lambda entity: menu_item_value(
            entity.device, ExtraMenuItem.HP_WATER_FLOW_TEMP, PropertyType.UNIT
        ),
        get_is_supported=lambda device: (
            menu_item_value(device, ExtraMenuItem.HP_WATER_FLOW_TEMP) is not None
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=str(ExtraMenuItem.CH_FLOW_TEMP),
        name=f"{NAME} CH flow measured temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: menu_item_value(
            entity.device, ExtraMenuItem.CH_FLOW_TEMP
        ),
        get_native_unit_of_measurement=lambda entity: menu_item_value(
            entity.device, ExtraMenuItem.CH_FLOW_TEMP, PropertyType.UNIT
        ),
        # Probably the same sensor as "CH flow temp": skip it when that one has a value.
        get_is_supported=lambda device: (
            menu_item_value(device, ExtraMenuItem.CH_FLOW_TEMP) is not None
            and device.ch_flow_temp_value is None
        ),
        system_types=[SystemType.GALEVO],
    ),
    *(
        AristonSensorEntityDescription(
            key=node,
            name=f"{NAME} {name}",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            get_native_value=lambda entity, node=node: menu_node_value(
                entity.device, node
            ),
            get_native_unit_of_measurement=lambda entity, node=node: menu_node_value(
                entity.device, node, PropertyType.UNIT
            ),
            get_is_supported=lambda device, node=node: (
                menu_node_value(device, node) is not None
            ),
            system_types=[SystemType.GALEVO],
        )
        for node, name in (
            (MenuNode.HP_RETURN_TEMP, "HP water return temp"),
            (MenuNode.HP_EVAPORATOR_TEMP, "HP evaporator temp"),
        )
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.OUTSIDE_TEMP,
        name=f"{NAME} Outside temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        device_features=[CustomDeviceFeatures.HAS_OUTSIDE_TEMP],
        get_native_value=lambda entity: entity.device.outside_temp_value,
        get_native_unit_of_measurement=lambda entity: entity.device.outside_temp_unit,
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
    AristonSensorEntityDescription(
        key=EvoLydosDeviceProperties.AV_SHW,
        name=f"{NAME} average showers",
        icon="mdi:shower-head",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.av_shw_value,
        native_unit_of_measurement="",
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
    AristonSensorEntityDescription(
        key="Gas consumption for heating last month",
        name=f"{NAME} gas consumption for heating last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: (
            entity.device.gas_consumption_for_heating_last_month
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Electricity consumption for heating last month",
        name=f"{NAME} electricity consumption for heating last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: (
            entity.device.electricity_consumption_for_heating_last_month
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Electricity consumption for cooling last month",
        name=f"{NAME} electricity consumption for cooling last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING, DeviceAttribute.HPMP_SYS],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: (
            entity.device.electricity_consumption_for_cooling_last_month
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Gas consumption for water last month",
        name=f"{NAME} gas consumption for water last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING, CustomDeviceFeatures.HAS_DHW],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: (
            entity.device.gas_consumption_for_water_last_month
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Electricity consumption for water last month",
        name=f"{NAME} electricity consumption for water last month",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[DeviceFeatures.HAS_METERING, CustomDeviceFeatures.HAS_DHW],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: (
            entity.device.electricity_consumption_for_water_last_month
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key="Central heating total energy consumption",
        name=f"{NAME} central heating total energy consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_TOTAL_ENERGY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: (
            entity.device.central_heating_total_energy_consumption
        ),
        get_last_reset=lambda entity: (
            entity.device.consumption_sequence_last_changed_utc
        ),
    ),
    AristonSensorEntityDescription(
        key="Domestic hot water total energy consumption",
        name=f"{NAME} domestic hot water total energy consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_TOTAL_ENERGY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: (
            entity.device.domestic_hot_water_total_energy_consumption
        ),
        get_last_reset=lambda entity: (
            entity.device.consumption_sequence_last_changed_utc
        ),
    ),
    AristonSensorEntityDescription(
        key="Central heating gas consumption",
        name=f"{NAME} central heating gas consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: entity.device.central_heating_gas_consumption,
        get_last_reset=lambda entity: (
            entity.device.consumption_sequence_last_changed_utc
        ),
    ),
    AristonSensorEntityDescription(
        key="Domestic hot water heating pump electricity consumption",
        name=f"{NAME} domestic hot water heating pump electricity consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_HEATING_PUMP_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: (
            entity.device.domestic_hot_water_heating_pump_electricity_consumption
        ),
        get_last_reset=lambda entity: (
            entity.device.consumption_sequence_last_changed_utc
        ),
    ),
    AristonSensorEntityDescription(
        key="Domestic hot water resistor electricity consumption",
        name=f"{NAME} domestic hot water resistor electricity consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_RESISTOR_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: (
            entity.device.domestic_hot_water_resistor_electricity_consumption
        ),
        get_last_reset=lambda entity: (
            entity.device.consumption_sequence_last_changed_utc
        ),
    ),
    AristonSensorEntityDescription(
        key="Domestic hot water gas consumption",
        name=f"{NAME} domestic hot water gas consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_GAS.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: (
            entity.device.domestic_hot_water_gas_consumption
        ),
        get_last_reset=lambda entity: (
            entity.device.consumption_sequence_last_changed_utc
        ),
    ),
    AristonSensorEntityDescription(
        key="Central heating electricity consumption",
        name=f"{NAME} central heating electricity consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.CENTRAL_HEATING_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: (
            entity.device.central_heating_electricity_consumption
        ),
        get_last_reset=lambda entity: (
            entity.device.consumption_sequence_last_changed_utc
        ),
    ),
    AristonSensorEntityDescription(
        key="Domestic hot water electricity consumption",
        name=f"{NAME} domestic hot water electricity consumption",
        icon="mdi:cash",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_features=[
            DeviceFeatures.HAS_METERING,
            ConsumptionType.DOMESTIC_HOT_WATER_ELECTRICITY.name,
        ],
        coordinator=ENERGY_COORDINATOR,
        get_native_value=lambda entity: (
            entity.device.domestic_hot_water_electricity_consumption
        ),
        get_last_reset=lambda entity: (
            entity.device.consumption_sequence_last_changed_utc
        ),
    ),
    AristonSensorEntityDescription(
        key=EvoDeviceProperties.RM_TM,
        name=f"{NAME} remaining time",
        icon="mdi:timer",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.rm_tm_in_minutes,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Lux,
            WheType.Evo,
            WheType.Evo2,
            WheType.Lux2,
            WheType.Lydos,
        ],
    ),
    AristonSensorEntityDescription(
        key=SlpDeviceSettings.SLP_HEATING_RATE,
        name=f"{NAME} heating rate",
        icon="mdi:chart-line",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.water_heater_heating_rate,
        native_unit_of_measurement="",
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonSensorEntityDescription(
        key=ARISTON_BUS_ERRORS,
        name=f"{NAME} errors count",
        icon="mdi:alert-outline",
        coordinator=BUS_ERRORS_COORDINATOR,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        get_native_value=lambda entity: len(entity.device.bus_errors),
        native_unit_of_measurement="",
        extra_states=[
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_ERRORS,
                EXTRA_STATE_DEVICE_METHOD: lambda entity: entity.device.bus_errors,
            },
        ],
    ),
    AristonSensorEntityDescription(
        key=EvoOneDeviceProperties.TEMP,
        name=f"{NAME} current temperature",
        icon="mdi:thermometer-auto",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.water_heater_current_temperature,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.Evo,
        ],
    ),
    AristonSensorEntityDescription(
        key=VelisDeviceProperties.PROC_REQ_TEMP,
        name=f"{NAME} proc req temp",
        icon="mdi:thermometer-auto",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.proc_req_temp_value,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        system_types=[SystemType.VELIS],
        whe_types=[
            WheType.NuosSplit,
            WheType.Evo2,
            WheType.LydosHybrid,
            WheType.Lydos,
            WheType.Andris2,
            WheType.Lux,
            WheType.Lux2,
        ],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.DHW_STORAGE_TEMPERATURE,
        name=f"{NAME} DHW current temperature",
        icon="mdi:thermometer-water",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.water_heater_current_temperature,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_features=[CustomDeviceFeatures.HAS_DHW],
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.DHW_TEMP,
        name=f"{NAME} DHW target temperature",
        icon="mdi:thermometer-chevron-up",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.water_heater_target_temperature,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_features=[CustomDeviceFeatures.HAS_DHW],
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
]


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
