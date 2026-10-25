"""Support for Ariston boilers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from ariston_net_api.const import BsbZoneMode, PlantMode, SystemType, ZoneMode
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_ECONOMY_TEMP,
    ATTR_HEAT_REQUEST,
    ATTR_ZONE,
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
class AristonClimateEntityDescription(
    ClimateEntityDescription, AristonBaseEntityDescription
):
    """A class that describes climate entities."""


ARISTON_CLIMATE_TYPES: list[AristonClimateEntityDescription] = [
    AristonClimateEntityDescription(
        key="AristonClimate",
        translation_key="thermostat",
        extra_states=[
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_HEAT_REQUEST,
                EXTRA_STATE_DEVICE_METHOD: lambda entity: (
                    entity.device.get_zone_heat_request_value(entity.zone)
                ),
            },
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_ECONOMY_TEMP,
                EXTRA_STATE_DEVICE_METHOD: lambda entity: (
                    entity.device.get_zone_economy_temp_value(entity.zone)
                ),
            },
            {
                EXTRA_STATE_ATTRIBUTE: ATTR_ZONE,
                EXTRA_STATE_DEVICE_METHOD: lambda entity: entity.zone,
            },
        ],
        system_types=[SystemType.GALEVO],
    ),
    AristonClimateEntityDescription(
        key="AristonClimate",
        translation_key="thermostat",
        system_types=[SystemType.BSB],
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AristonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Ariston device from config entry."""
    ariston_climates: list[AristonThermostat] = []

    for description in ARISTON_CLIMATE_TYPES:
        coordinator = entry.runtime_data.get_coordinator(description.coordinator)
        if is_entity_supported(coordinator, description):
            for zone_number in coordinator.device.zone_numbers:
                ariston_climates.append(
                    AristonThermostat(
                        zone_number,
                        coordinator,
                        description,
                    )
                )

    async_add_entities(ariston_climates)


class AristonThermostat(AristonEntity, ClimateEntity):
    """Ariston Thermostat Device."""

    _attr_name = None
    entity_description: AristonClimateEntityDescription

    def __init__(
        self,
        zone: int,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonClimateEntityDescription,
    ) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator, description, zone)
        self._attr_unique_id = f"{self.device.gateway}_{zone}"

    @property
    def icon(self):
        """Return the icon of the thermostat device."""
        if self.device.is_plant_in_heat_mode:
            return "mdi:radiator"
        return "mdi:radiator-off"

    @property
    def temperature_unit(self) -> str:
        """Return the temperature units for the device."""
        return self.device.get_measured_temp_unit(self.zone)

    @property
    def precision(self) -> float:
        """Return the precision of temperature for the device."""
        return 1 / 10 ** self.device.get_measured_temp_decimals(self.zone)

    @property
    def min_temp(self):
        """Return minimum temperature."""
        return self.device.get_comfort_temp_min(self.zone)

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self.device.get_comfort_temp_max(self.zone)

    @property
    def target_temperature_step(self) -> float:
        """Return the target temperature step support by the device."""
        return self.device.get_target_temp_step(self.zone)

    @property
    def current_temperature(self) -> float:
        """Return the reported current temperature for the device."""
        return self.device.get_measured_temp_value(self.zone)

    @property
    def target_temperature(self) -> float:
        """Return the target temperature for the device."""
        return self.device.get_target_temp_value(self.zone)

    @property
    def supported_features(self) -> int:
        """Return the supported features for this device integration."""
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )
        return (
            features | ClimateEntityFeature.PRESET_MODE
            if self.device.plant_mode_supported
            else features
        )

    @property
    def hvac_mode(self) -> str:
        """Return the current HVAC mode for the device."""
        curr_hvac_mode = HVACMode.OFF

        if self.device.is_plant_in_heat_mode:
            if self.device.is_zone_in_manual_mode(self.zone):
                curr_hvac_mode = HVACMode.HEAT
            elif self.device.is_zone_in_time_program_mode(self.zone):
                curr_hvac_mode = HVACMode.AUTO
        if self.device.is_plant_in_cool_mode:
            if self.device.is_zone_in_manual_mode(self.zone):
                curr_hvac_mode = HVACMode.COOL
            elif self.device.is_zone_in_time_program_mode(self.zone):
                curr_hvac_mode = HVACMode.AUTO
        return curr_hvac_mode

    @property
    def hvac_modes(self) -> list[str]:
        """Return the HVAC modes support by the device."""
        supported_modes = []
        if self._zone_mode_offered(self.device.is_zone_mode_options_contains_manual):
            supported_modes.append(HVACMode.HEAT)
            if (
                self.device.plant_mode_supported
                and self.device.is_plant_mode_options_contains_cooling
            ):
                supported_modes.append(HVACMode.COOL)
        if self._zone_mode_offered(
            self.device.is_zone_mode_options_contains_time_program
        ):
            supported_modes.append(HVACMode.AUTO)
        # Some Nimbus zones have no OFF option, but the plant mode can still
        # turn heating off (OFF or SUMMER, see async_set_hvac_mode).
        if self.device.plant_mode_supported or self._zone_mode_offered(
            self.device.is_zone_mode_options_contains_off
        ):
            supported_modes.append(HVACMode.OFF)

        return supported_modes

    @property
    def hvac_action(self):
        """Return the current running hvac operation."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        if_flame_on = bool(self.device.is_flame_on_value)
        if_heating_pump_on = bool(
            getattr(self.device, "is_heating_pump_on_value", False)
        )

        if_not_idle = if_flame_on or if_heating_pump_on

        curr_hvac_action = HVACAction.OFF
        if self.device.is_plant_in_heat_mode:
            # The flame or pump may run for hot water only. BSB has no request.
            get_request = getattr(self.device, "get_zone_heat_request_value", None)
            heat_request = get_request(self.zone) if get_request else None
            if heat_request is not None:
                if_not_idle = if_not_idle and bool(heat_request)
            curr_hvac_action = HVACAction.HEATING if if_not_idle else HVACAction.IDLE
        if self.device.is_plant_in_cool_mode:
            curr_hvac_action = HVACAction.COOLING if if_not_idle else HVACAction.IDLE
        return curr_hvac_action

    @property
    def preset_mode(self) -> str:
        """Return the current preset mode, e.g., home, away, temp."""
        return self.device.plant_mode_text

    @property
    def preset_modes(self) -> list[str]:
        """Return a list of available preset modes."""
        return self.device.plant_mode_opt_texts

    @cloud_action
    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if self.device.plant_mode_supported:
            plant_modes = self.device.plant_mode_options
            zone_modes = self._zone_mode_options
            current_plant_mode = self.device.plant_mode

            if hvac_mode == HVACMode.OFF:
                if self.device.is_plant_mode_options_contains_off:
                    await self._async_set_plant_mode(PlantMode.OFF)
                else:
                    await self._async_set_plant_mode(PlantMode.SUMMER)
            elif hvac_mode == HVACMode.AUTO:
                if current_plant_mode in [
                    PlantMode.WINTER,
                    PlantMode.HEATING_ONLY,
                    PlantMode.COOLING,
                ]:
                    # if already heating or cooling just change CH mode
                    pass
                elif current_plant_mode == PlantMode.SUMMER:
                    # DHW is working, so use Winter where CH and DHW are active
                    await self._async_set_plant_mode(PlantMode.WINTER)
                # hvac is OFF, so use heating only, if not supported then winter
                elif PlantMode.HEATING_ONLY.value in plant_modes:
                    await self._async_set_plant_mode(PlantMode.HEATING_ONLY)
                else:
                    await self._async_set_plant_mode(PlantMode.WINTER)
                await self._async_set_zone_mode(ZoneMode.TIME_PROGRAM)
            elif hvac_mode == HVACMode.HEAT:
                if current_plant_mode in [PlantMode.WINTER, PlantMode.HEATING_ONLY]:
                    # if already heating, change CH mode
                    pass
                elif current_plant_mode in [PlantMode.SUMMER, PlantMode.COOLING]:
                    # DHW is working, so use Winter and change mode
                    await self._async_set_plant_mode(PlantMode.WINTER)
                # hvac is OFF, so use heating only, if not supported then winter
                elif PlantMode.HEATING_ONLY.value in plant_modes:
                    await self._async_set_plant_mode(PlantMode.HEATING_ONLY)
                else:
                    await self._async_set_plant_mode(PlantMode.WINTER)
                await self._async_set_zone_mode(self._manual_zone_mode(zone_modes))
            elif hvac_mode == HVACMode.COOL:
                await self._async_set_plant_mode(PlantMode.COOLING)
                await self._async_set_zone_mode(self._manual_zone_mode(zone_modes))
        # Plant mode is not supported (BSB device)
        elif hvac_mode == HVACMode.OFF:
            await self._async_set_zone_mode(BsbZoneMode.OFF)
        elif hvac_mode == HVACMode.AUTO:
            await self._async_set_zone_mode(BsbZoneMode.TIME_PROGRAM)
        elif hvac_mode == HVACMode.HEAT:
            await self._async_set_zone_mode(BsbZoneMode.MANUAL)

        # The plant mode select shows the change too.
        self.coordinator.async_update_listeners()

    async def _async_set_plant_mode(self, plant_mode: PlantMode) -> None:
        """Set the plant mode, unless the device already has it."""
        if self.device.plant_mode != plant_mode:
            await self.device.async_set_plant_mode(plant_mode)

    async def _async_set_zone_mode(self, zone_mode: ZoneMode | BsbZoneMode) -> None:
        """Set the zone mode, unless the zone already has it."""
        if self.device.get_zone_mode(self.zone) != zone_mode:
            await self.device.async_set_zone_mode(zone_mode, self.zone)

    @property
    def _zone_mode_options(self) -> list[int]:
        """Return the zone mode options, empty when the cloud sends none."""
        return self.device.get_zone_mode_options(self.zone) or []

    def _zone_mode_offered(self, contains: Callable[[int], bool]) -> bool:
        """Return if the zone offers a mode, without failing on no options."""
        return bool(self._zone_mode_options) and contains(self.zone)

    @staticmethod
    def _manual_zone_mode(zone_modes: list[int]) -> ZoneMode:
        """Return the manual zone mode the device offers."""
        if ZoneMode.MANUAL_NIGHT.value in zone_modes:
            return ZoneMode.MANUAL_NIGHT
        return ZoneMode.MANUAL

    @cloud_action
    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        _LOGGER.debug(
            "Setting preset mode to %s for %s",
            preset_mode,
            self.entity_id,
        )

        # Don't assume index maps to enum value directly
        preset_index = self.device.plant_mode_opt_texts.index(preset_mode)
        plant_mode = PlantMode(self.device.plant_mode_options[preset_index])

        # Get current states
        current_plant_in_cool = self.device.is_plant_in_cool_mode
        zone_modes = self._zone_mode_options
        zone_is_off = self.device.get_zone_mode(self.zone) == ZoneMode.OFF

        # When leaving cooling, set the zone to manual heat before the plant mode
        if (
            current_plant_in_cool
            and plant_mode != PlantMode.COOLING
            and ZoneMode.MANUAL.value in zone_modes
        ):
            await self._async_set_zone_mode(ZoneMode.MANUAL)
            zone_is_off = False

        # Set the plant mode
        await self._async_set_plant_mode(plant_mode)

        # Special handling for OFF mode
        if plant_mode == PlantMode.OFF:
            if self._zone_mode_offered(self.device.is_zone_mode_options_contains_off):
                await self._async_set_zone_mode(ZoneMode.OFF)
        # The OFF preset turns the zone off, so turn it on again to heat or cool
        elif zone_is_off and plant_mode in [
            PlantMode.WINTER,
            PlantMode.HEATING_ONLY,
            PlantMode.COOLING,
            PlantMode.COOLING_ONLY,
        ]:
            await self._async_set_zone_mode(self._manual_zone_mode(zone_modes))

        # The library keeps the new modes, so no refresh. The plant mode select
        # shows them too.
        self.coordinator.async_update_listeners()

    @cloud_action
    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="missing_temperature"
            )

        temperature = kwargs[ATTR_TEMPERATURE]
        _LOGGER.debug(
            "Setting temperature to %s for %s",
            temperature,
            self.entity_id,
        )

        if temperature == self.device.get_comfort_temp_value(self.zone):
            return
        await self.device.async_set_comfort_temp(temperature, self.zone)
        self.async_write_ha_state()
