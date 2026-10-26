"""Support for Ariston sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ariston_net_api.const import (
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
    MeteringPeriod,
    MeteringSeries,
    MeteringTab,
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
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_ERRORS,
    BUS_ERRORS_COORDINATOR,
    ENERGY_COORDINATOR,
    EXTRA_STATE_ATTRIBUTE,
    EXTRA_STATE_DEVICE_METHOD,
    METERING_COORDINATOR,
    NAME,
)
from .coordinator import AristonConfigEntry, DeviceDataUpdateCoordinator
from .entity import AristonBaseEntityDescription, AristonEntity, is_entity_supported
from .menu_items import ExtraMenuItem, MenuNode, menu_item_value, menu_node_value

# The library uses this reset time until the energy data changes once.
UNKNOWN_RESET = datetime.fromtimestamp(0, UTC)


PARALLEL_UPDATES = 0


@dataclass(kw_only=True, frozen=True)
class AristonSensorEntityDescription(
    SensorEntityDescription, AristonBaseEntityDescription
):
    """A class that describes sensor entities."""

    get_native_unit_of_measurement: Callable[[Any], str] | None = None
    get_last_reset: Callable[[Any], datetime] | None = None
    get_available: Callable[[Any], bool] | None = None
    get_native_value: Callable[[Any], Any]


MIN_COP_ELECTRICITY_KWH = 0.5


def _can_cool(device: Any) -> bool:
    """Return True if a plant mode can cool."""
    # The cloud sends cooling rows also for devices that cannot cool.
    return (
        device.plant_mode_options is not None
        and device.is_plant_mode_options_contains_cooling
    )


def _is_not_hybrid(device: Any) -> bool:
    """Return True if the plant has no gas boiler next to the heat pump."""
    # A hybrid's heat produced may hold the boiler's heat, so its COP means nothing.
    return device.features.get(DeviceFeatures.HYBRID_SYS) is not True


def _is_metering_on(entity: Any) -> bool:
    """Return False while the web app shows metering as off."""
    return not entity.device.is_metering_intensive_logs_active


def _metering_features(series: MeteringSeries) -> list[str] | None:
    """Return the features a metering series needs."""
    return [CustomDeviceFeatures.HAS_DHW] if series is MeteringSeries.DHW else None


def _cop(device: Any, series: MeteringSeries, period: MeteringPeriod) -> float | None:
    """Return the energy produced per kWh of electricity used."""
    produced = device.get_metering_total(MeteringTab.PRODUCED_ENERGY, series, period)
    used = device.get_metering_total(MeteringTab.CONSUMED_ELECTRICITY, series, period)
    # Less electricity gives a COP far from the real one.
    if produced is None or used is None or used < MIN_COP_ELECTRICITY_KWH:
        return None
    return produced / used


def _produced_energy_description(
    key: str,
    name: str,
    series: MeteringSeries,
    period: MeteringPeriod,
    state_class: SensorStateClass | None,
) -> AristonSensorEntityDescription:
    """Describe a sensor of the energy produced in a period."""
    return AristonSensorEntityDescription(
        key=key,
        name=name,
        translation_key=key,
        state_class=state_class,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        device_features=_metering_features(series),
        system_types=[SystemType.GALEVO],
        coordinator=METERING_COORDINATOR,
        get_is_supported=_can_cool if series is MeteringSeries.COOLING else None,
        get_available=_is_metering_on,
        get_native_value=lambda entity: entity.device.get_metering_total(
            MeteringTab.PRODUCED_ENERGY, series, period
        ),
    )


def _cop_description(
    key: str, name: str, series: MeteringSeries, period: MeteringPeriod
) -> AristonSensorEntityDescription:
    """Describe a sensor of the COP in a period."""
    return AristonSensorEntityDescription(
        key=key,
        name=name,
        translation_key=key,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        device_features=_metering_features(series),
        system_types=[SystemType.GALEVO],
        coordinator=METERING_COORDINATOR,
        get_is_supported=_is_not_hybrid,
        get_available=_is_metering_on,
        get_native_value=lambda entity: _cop(entity.device, series, period),
    )


ARISTON_SENSOR_TYPES: list[AristonSensorEntityDescription] = [
    AristonSensorEntityDescription(
        key=DeviceProperties.HEATING_CIRCUIT_PRESSURE,
        name=f"{NAME} heating circuit pressure",
        translation_key="heating_circuit_pressure",
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
        translation_key="ch_flow_setpoint_temperature",
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
        translation_key="ch_flow_temperature",
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
        translation_key="signal_strength",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        get_native_value=lambda entity: entity.device.signal_strength_value,
        get_native_unit_of_measurement=lambda entity: (
            entity.device.signal_strength_unit
        ),
        system_types=[SystemType.GALEVO],
    ),
    AristonSensorEntityDescription(
        key=str(MenuItemNames.CH_RETURN_TEMP),
        name=f"{NAME} CH return temp",
        translation_key="ch_return_temperature",
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
        translation_key="hp_flow_temperature",
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
        translation_key="ch_flow_measured_temperature",
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
            translation_key=translation_key,
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
        for node, name, translation_key in (
            (
                MenuNode.HP_RETURN_TEMP,
                "HP water return temp",
                "hp_return_temperature",
            ),
            (
                MenuNode.HP_EVAPORATOR_TEMP,
                "HP evaporator temp",
                "hp_evaporator_temperature",
            ),
        )
    ),
    AristonSensorEntityDescription(
        key=DeviceProperties.OUTSIDE_TEMP,
        name=f"{NAME} Outside temp",
        translation_key="outside_temperature",
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
        translation_key="average_showers",
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
        translation_key="heating_gas_last_month",
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
        translation_key="heating_electricity_last_month",
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
        translation_key="cooling_electricity_last_month",
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
        translation_key="dhw_gas_last_month",
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
        translation_key="dhw_electricity_last_month",
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
        translation_key="heating_energy",
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
        translation_key="dhw_energy",
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
        translation_key="heating_gas",
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
        translation_key="dhw_heat_pump_electricity",
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
        translation_key="dhw_resistor_electricity",
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
        translation_key="dhw_gas",
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
        translation_key="heating_electricity",
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
        translation_key="dhw_electricity",
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
    # "Today" keeps no statistics: polls miss the end of each day. "This month" does.
    _produced_energy_description(
        "heating_produced_today",
        f"{NAME} heating energy produced today",
        MeteringSeries.HEATING,
        MeteringPeriod.CURRENT_DAY,
        None,
    ),
    _produced_energy_description(
        "dhw_produced_today",
        f"{NAME} DHW energy produced today",
        MeteringSeries.DHW,
        MeteringPeriod.CURRENT_DAY,
        None,
    ),
    _produced_energy_description(
        "cooling_produced_today",
        f"{NAME} cooling energy produced today",
        MeteringSeries.COOLING,
        MeteringPeriod.CURRENT_DAY,
        None,
    ),
    _produced_energy_description(
        "heating_produced_this_month",
        f"{NAME} heating energy produced this month",
        MeteringSeries.HEATING,
        MeteringPeriod.CURRENT_MONTH,
        SensorStateClass.TOTAL_INCREASING,
    ),
    _produced_energy_description(
        "dhw_produced_this_month",
        f"{NAME} DHW energy produced this month",
        MeteringSeries.DHW,
        MeteringPeriod.CURRENT_MONTH,
        SensorStateClass.TOTAL_INCREASING,
    ),
    _produced_energy_description(
        "cooling_produced_this_month",
        f"{NAME} cooling energy produced this month",
        MeteringSeries.COOLING,
        MeteringPeriod.CURRENT_MONTH,
        SensorStateClass.TOTAL_INCREASING,
    ),
    _cop_description(
        "heating_cop_yesterday",
        f"{NAME} heating COP yesterday",
        MeteringSeries.HEATING,
        MeteringPeriod.PREVIOUS_DAY,
    ),
    _cop_description(
        "dhw_cop_yesterday",
        f"{NAME} DHW COP yesterday",
        MeteringSeries.DHW,
        MeteringPeriod.PREVIOUS_DAY,
    ),
    _cop_description(
        "heating_cop_this_month",
        f"{NAME} heating COP this month",
        MeteringSeries.HEATING,
        MeteringPeriod.CURRENT_MONTH,
    ),
    _cop_description(
        "dhw_cop_this_month",
        f"{NAME} DHW COP this month",
        MeteringSeries.DHW,
        MeteringPeriod.CURRENT_MONTH,
    ),
    AristonSensorEntityDescription(
        key=EvoDeviceProperties.RM_TM,
        name=f"{NAME} remaining time",
        translation_key="remaining_time",
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
        translation_key="heating_rate",
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.water_heater_heating_rate,
        native_unit_of_measurement="",
        system_types=[SystemType.VELIS],
        whe_types=[WheType.NuosSplit],
    ),
    AristonSensorEntityDescription(
        key=ARISTON_BUS_ERRORS,
        name=f"{NAME} errors count",
        translation_key="errors_count",
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
        translation_key="current_temperature",
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
        translation_key="requested_temperature",
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
        translation_key="dhw_temperature",
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
        translation_key="dhw_target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        get_native_value=lambda entity: entity.device.water_heater_target_temperature,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_features=[CustomDeviceFeatures.HAS_DHW],
        system_types=[SystemType.GALEVO, SystemType.BSB],
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
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
    if (
        not energy_coordinator
        or energy_coordinator.last_update_success
        or not skipped_energy_descriptions
    ):
        return

    # Energy features are known only after the first good energy update.
    @callback
    def async_add_energy_sensors() -> None:
        """Add the energy sensors once energy data is available, then stop."""
        if not energy_coordinator.last_update_success:
            return
        async_add_entities(
            AristonSensor(energy_coordinator, description)
            for description in skipped_energy_descriptions
            if is_entity_supported(energy_coordinator, description)
        )
        skipped_energy_descriptions.clear()
        remove_listener()

    @callback
    def async_remove_listener() -> None:
        """Stop waiting for energy data when the entry unloads."""
        if skipped_energy_descriptions:
            remove_listener()

    remove_listener = energy_coordinator.async_add_listener(async_add_energy_sensors)
    entry.async_on_unload(async_remove_listener)


class AristonSensor(AristonEntity, SensorEntity):
    """Base class for specific ariston sensors."""

    entity_description: AristonSensorEntityDescription

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonSensorEntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description)

    @property
    def available(self) -> bool:
        """Return True if the coordinator works and the sensor has data."""
        return super().available and (
            self.entity_description.get_available is None
            or self.entity_description.get_available(self)
        )

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
