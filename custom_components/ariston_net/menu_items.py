"""Extra cloud menu items, read together with the ones the library asks for."""

from __future__ import annotations

from enum import IntEnum
import logging
from typing import Any

from ariston.ariston_api import AristonAPI, ConnectionException
from ariston.base_device import AristonBaseDevice
from ariston.const import ARISTON_MENU_ITEMS, MenuItemNames, PropertyType

_LOGGER = logging.getLogger(__name__)

HTTP_TOO_MANY_REQUESTS = 429


class ExtraMenuItem(IntEnum):
    """Menu items the library does not ask for."""

    HP_WATER_FLOW_TEMP = 348
    CH_FLOW_TEMP = 349


def menu_item_value(
    device: AristonBaseDevice,
    item_id: int,
    field: str = PropertyType.VALUE,
) -> Any:
    """Return a field of a menu item, or None when the cloud did not send it."""
    return next(
        (
            item.get(field)
            for item in getattr(device, "menu_items", [])
            if item.get("id") == item_id
        ),
        None,
    )


def add_extra_menu_items(api: AristonAPI, api_url: str) -> None:
    """Ask for the extra menu items in the library's own menu items request.

    The library builds that request from a fixed list. Replacing the method on
    this API object adds the extra items without a second cloud request. If the
    cloud refuses the longer list (a model without these items), it goes back to
    the library's list for good.
    """
    library_get_menu_items = api.async_get_menu_items
    item_ids = ",".join(
        [MenuItemNames.values(), *(str(item.value) for item in ExtraMenuItem)]
    )
    use_extra_items = True

    async def async_get_menu_items(gw_id: str) -> list[dict[str, Any]]:
        nonlocal use_extra_items
        if use_extra_items:
            try:
                items = await api._async_get(
                    f"{api_url}{ARISTON_MENU_ITEMS}/{gw_id}?menuItems={item_ids}"
                )
            except ConnectionException as error:
                # Rate limiting is not about the item list: let the coordinator back off.
                if error.args and error.args[0] == HTTP_TOO_MANY_REQUESTS:
                    raise
                use_extra_items = False
                _LOGGER.debug(
                    "The cloud refused the extra menu items (%s), asking for the "
                    "library's items only",
                    error,
                )
            else:
                return items if items is not None else []
        return await library_get_menu_items(gw_id)

    api.async_get_menu_items = async_get_menu_items  # type: ignore[method-assign]
