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
REFUSALS_BEFORE_FALLBACK = 3


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
    cloud refuses the longer list in several polls in a row while the library's
    list works, it goes back to the library's list until the next reload.
    """
    if not callable(getattr(api, "_async_get", None)):
        _LOGGER.warning(
            "This ariston library version has no _async_get, so the extra menu "
            "items are not read"
        )
        return

    library_get_menu_items = api.async_get_menu_items
    item_ids = ",".join(
        [MenuItemNames.values(), *(str(item.value) for item in ExtraMenuItem)]
    )
    refused = 0

    async def async_get_menu_items(gw_id: str) -> list[dict[str, Any]]:
        nonlocal refused
        if refused >= REFUSALS_BEFORE_FALLBACK:
            return await library_get_menu_items(gw_id)
        try:
            items = await api._async_get(
                f"{api_url}{ARISTON_MENU_ITEMS}/{gw_id}?menuItems={item_ids}"
            )
        except ConnectionException as error:
            status = error.args[0] if error.args else None
            # Auth errors carry text, and 429 is for the coordinator backoff.
            if not isinstance(status, int) or status == HTTP_TOO_MANY_REQUESTS:
                raise
            items = await library_get_menu_items(gw_id)
            refused += 1
            if refused == REFUSALS_BEFORE_FALLBACK:
                _LOGGER.warning(
                    "The cloud refused the extra menu items %s times in a row "
                    "(HTTP %s), asking for the library's items only",
                    refused,
                    status,
                )
            return items
        refused = 0
        return items if items is not None else []

    api.async_get_menu_items = async_get_menu_items  # type: ignore[method-assign]
