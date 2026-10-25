"""Entity object for shared properties of Ariston entities."""

from __future__ import annotations

from abc import ABC
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, Concatenate

from ariston_net_api.const import SystemType, WheType
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COORDINATOR, DOMAIN, EXTRA_STATE_ATTRIBUTE, EXTRA_STATE_DEVICE_METHOD
from .coordinator import DeviceDataUpdateCoordinator
from .errors import CLOUD_ERRORS, action_error


@dataclass(kw_only=True, frozen=True)
class AristonBaseEntityDescription(EntityDescription):
    """An abstract class that describes Ariston entites."""

    device_features: list[str] | None = None
    coordinator: str = COORDINATOR
    extra_states: list[dict[str, Any]] | None = None
    system_types: list[SystemType] | None = None
    whe_types: list[WheType] | None = None
    zone: bool = False
    # Checked once at setup with the device; False skips the entity.
    get_is_supported: Callable[[Any], bool] | None = None


def is_entity_supported(
    coordinator: DeviceDataUpdateCoordinator | None,
    description: AristonBaseEntityDescription,
) -> bool:
    """Return True if the device has the features and the data for the entity."""
    if not coordinator or not coordinator.device:
        return False
    device = coordinator.device
    if not device.are_device_features_available(
        description.device_features,
        description.system_types,
        description.whe_types,
    ):
        return False
    return description.get_is_supported is None or bool(
        description.get_is_supported(device)
    )


class AristonEntity(CoordinatorEntity[DeviceDataUpdateCoordinator], ABC):
    """Generic Ariston entity (base class)."""

    _attr_has_entity_name = True
    entity_description: AristonBaseEntityDescription

    def __init__(
        self,
        coordinator: DeviceDataUpdateCoordinator,
        description: AristonBaseEntityDescription,
        zone: int = 0,
        unique_id_name: str | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)

        self.device = coordinator.device
        self.entity_description = description
        self.zone = zone
        # Unique IDs keep the old names, so never change description.name.
        name = unique_id_name or description.name
        self._attr_unique_id = (
            f"{self.device.gateway}-{name}-{zone}"
            if zone
            else f"{self.device.gateway}-{name}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device.serial_number or "")},
            manufacturer="Ariston",
            name=self.device.name,
            sw_version=self.device.firmware_version,
            model=self.model,
        )

    @property
    def model(self) -> str:
        """Return the model of the entity."""
        if self.device.whe_model_type == 0:
            if self.device.whe_type is WheType.Unknown:
                return f"{self.device.system_type.name}"
            return f"{self.device.system_type.name} {self.device.whe_type.name}"
        return f"{self.device.system_type.name} {self.device.whe_type.name} | Model {self.device.whe_model_type}"

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        state_attributes = {}

        if self.entity_description.extra_states is None:
            return None

        for extra_state in self.entity_description.extra_states:
            device_method = extra_state.get(EXTRA_STATE_DEVICE_METHOD)

            if device_method is None:
                continue

            state_attribute = device_method(self)

            if state_attribute is None:
                continue

            state_attributes[extra_state.get(EXTRA_STATE_ATTRIBUTE)] = state_attribute

        return state_attributes


def cloud_action[E: AristonEntity, **P, R](
    func: Callable[Concatenate[E, P], Awaitable[R]],
) -> Callable[Concatenate[E, P], Awaitable[R]]:
    """Show cloud errors of an entity action as HA errors, without a traceback."""

    @wraps(func)
    async def wrapper(self: E, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(self, *args, **kwargs)
        except CLOUD_ERRORS as error:
            # Earlier writes of the action may have worked, so show them.
            self.coordinator.async_update_listeners()
            raise action_error(
                self.hass, self.coordinator.config_entry, error
            ) from error

    return wrapper
