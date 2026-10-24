"""Tests for the Ariston NET data update coordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

from ariston import AristonGalevoDevice
from ariston.ariston_api import ConnectionException
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import COORDINATOR
from custom_components.ariston_net.coordinator import DeviceDataUpdateCoordinator

SCAN_INTERVAL = timedelta(seconds=180)


async def test_rate_limit_backs_off_and_recovers(
    hass: HomeAssistant, config_entry: MockConfigEntry, device: AristonGalevoDevice
) -> None:
    """Test 429 doubles the interval up to 8x and a good update restores it."""
    update = AsyncMock(side_effect=ConnectionException(429, "body"))
    coordinator = DeviceDataUpdateCoordinator(
        hass,
        config_entry,
        device,
        int(SCAN_INTERVAL.total_seconds()),
        COORDINATOR,
        update,
    )

    for factor in (2, 4, 8, 8):
        await coordinator.async_refresh()
        assert not coordinator.last_update_success
        assert coordinator.update_interval == SCAN_INTERVAL * factor

    update.side_effect = None
    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.update_interval == SCAN_INTERVAL


async def test_rate_limit_backoff_is_kept_on_other_errors(
    hass: HomeAssistant, config_entry: MockConfigEntry, device: AristonGalevoDevice
) -> None:
    """Test other errors don't reset the backoff."""
    update = AsyncMock(side_effect=ConnectionException(429, "body"))
    coordinator = DeviceDataUpdateCoordinator(
        hass,
        config_entry,
        device,
        int(SCAN_INTERVAL.total_seconds()),
        COORDINATOR,
        update,
    )
    await coordinator.async_refresh()

    update.side_effect = ConnectionException(500)
    await coordinator.async_refresh()

    assert coordinator.update_interval == SCAN_INTERVAL * 2


@pytest.mark.parametrize(
    "error",
    [
        ConnectionException(500),
        ConnectionException(),
        ConnectionException("Invalid token"),
        ConnectionException("429"),
    ],
    ids=["500", "no-args", "invalid-token", "text-429"],
)
async def test_other_connection_errors_are_raised(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: AristonGalevoDevice,
    error: ConnectionException,
) -> None:
    """Test errors other than 429 are raised unchanged."""
    coordinator = DeviceDataUpdateCoordinator(
        hass,
        config_entry,
        device,
        int(SCAN_INTERVAL.total_seconds()),
        COORDINATOR,
        AsyncMock(side_effect=error),
    )

    with pytest.raises(ConnectionException) as exc_info:
        await coordinator._async_update_data()

    assert exc_info.value is error
    assert coordinator.update_interval == SCAN_INTERVAL
