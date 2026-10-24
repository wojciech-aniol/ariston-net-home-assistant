"""Support for Ariston sensors."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import ARISTON_SELECT_TYPES, DOMAIN, AristonSelectEntityDescription
from .coordinator import DeviceDataUpdateCoordinator
from .entity import AristonEntity, is_entity_supported


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the Ariston selects from config entry."""
    ariston_select: list[AristonSelect] = []

    for description in ARISTON_SELECT_TYPES:
        coordinator: DeviceDataUpdateCoordinator = hass.data[DOMAIN][entry.unique_id][
            description.coordinator
        ]
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
