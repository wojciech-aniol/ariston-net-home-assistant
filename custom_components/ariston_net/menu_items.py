"""Extra cloud menu items, read together with the ones the library asks for."""

from __future__ import annotations

from collections.abc import Iterable
from enum import IntEnum, StrEnum
import logging
from typing import Any

import aiohttp
from ariston_net_api.ariston_api import AristonAPI, ConnectionException
from ariston_net_api.base_device import AristonBaseDevice
from ariston_net_api.const import ARISTON_MENU_ITEMS, MenuItemNames, PropertyType

from .errors import CloudErrorKind, classify_error, error_status

_LOGGER = logging.getLogger(__name__)

REFUSALS_BEFORE_FALLBACK = 3

# The cloud fails the whole request (HTTP 500) when it holds one of these IDs.
# They are the heat pump nodes T_13.8.2 to T_13.8.7, so they are checked only at setup.
BLOCKED_MENU_IDS = range(342, 348)


class ExtraMenuItem(IntEnum):
    """Menu items the library does not ask for."""

    HP_WATER_FLOW_TEMP = 348
    CH_FLOW_TEMP = 349


class MenuNode(StrEnum):
    """Menu nodes that the cloud refuses for an owner account so far."""

    HP_RETURN_TEMP = "T_13.8.2"
    HP_EVAPORATOR_TEMP = "T_13.8.7"


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


def menu_node_value(
    device: AristonBaseDevice,
    node: str,
    field: str = PropertyType.VALUE,
) -> Any:
    """Return a field of the menu item of a node, or None when the cloud did not send it."""
    return next(
        (
            item.get(field)
            for item in getattr(device, "menu_items", [])
            if item.get("nodeId") == node
        ),
        None,
    )


async def async_find_blocked_menu_items(
    api: AristonAPI, api_url: str, gw_id: str
) -> list[int]:
    """Return the IDs of the MenuNode items the cloud serves now, for setup only.

    One request, apart from the polled one. While the cloud refuses these IDs,
    nothing else changes.
    """
    if not callable(getattr(api, "_async_get", None)):
        return []
    item_ids = ",".join(str(item_id) for item_id in BLOCKED_MENU_IDS)
    try:
        items = await api._async_get(
            f"{api_url}{ARISTON_MENU_ITEMS}/{gw_id}?menuItems={item_ids}"
        )
    except (TimeoutError, ConnectionException, aiohttp.ClientError) as error:
        _LOGGER.debug("The cloud still refuses menu items %s (%s)", item_ids, error)
        return []
    found = [
        item["id"]
        for item in items or []
        if item.get("nodeId") in set(MenuNode) and item.get("value") is not None
    ]
    if found:
        _LOGGER.info("The cloud now serves menu items %s, reading them", found)
    return found


def add_extra_menu_items(
    api: AristonAPI, api_url: str, more_ids: Iterable[int] = ()
) -> None:
    """Ask for the extra menu items in the library's own menu items request.

    The library builds that request from a fixed list. Replacing the method on
    this API object adds the extra items (and more_ids) without a second cloud
    request. If the cloud refuses the longer list in several polls in a row
    while the library's list works, it goes back to the library's list until
    the next reload.
    """
    if not callable(getattr(api, "_async_get", None)):
        _LOGGER.warning(
            "This ariston library version has no _async_get, so the extra menu "
            "items are not read"
        )
        return

    library_get_menu_items = api.async_get_menu_items
    item_ids = ",".join(
        [
            MenuItemNames.values(),
            *(str(item.value) for item in ExtraMenuItem),
            *(str(item_id) for item_id in more_ids),
        ]
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
            status = error_status(error)
            # Auth errors and 429 are for the coordinator.
            if status is None or classify_error(error) in (
                CloudErrorKind.AUTH,
                CloudErrorKind.RATE_LIMIT,
            ):
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
