"""Tests for the Ariston NET data update coordinator."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from ariston import AristonGalevoDevice
from ariston.ariston_api import ConnectionException
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import COORDINATOR, DOMAIN
from custom_components.ariston_net.coordinator import DeviceDataUpdateCoordinator

from .conftest import tracebacks

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


def make_coordinator(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    device: AristonGalevoDevice,
    error: ConnectionException,
) -> DeviceDataUpdateCoordinator:
    """Return a coordinator whose update raises the error."""
    return DeviceDataUpdateCoordinator(
        hass,
        entry,
        device,
        int(SCAN_INTERVAL.total_seconds()),
        COORDINATOR,
        AsyncMock(side_effect=error),
    )


@pytest.mark.parametrize(
    "error",
    [
        ConnectionException(500),
        ConnectionException(),
        ConnectionException(400),
        ConnectionException("429"),
    ],
    ids=["500", "no-args", "400", "text-429"],
)
async def test_other_connection_errors_raise_update_failed(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: AristonGalevoDevice,
    error: ConnectionException,
) -> None:
    """Test errors other than auth and 429 fail the update without a backoff."""
    coordinator = make_coordinator(hass, config_entry, device, error)

    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()

    assert exc_info.value.translation_key == "update_failed"
    assert exc_info.value.__cause__ is error
    assert coordinator.update_interval == SCAN_INTERVAL


async def test_update_failed_names_status(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: AristonGalevoDevice,
) -> None:
    """Test the update error carries the HTTP status for the message."""
    coordinator = make_coordinator(hass, config_entry, device, ConnectionException(503))

    with pytest.raises(UpdateFailed) as exc_info:
        await coordinator._async_update_data()

    assert exc_info.value.translation_placeholders == {"error": "HTTP 503"}


@pytest.mark.parametrize(
    "error",
    [
        ConnectionException("Invalid token"),
        ConnectionException("Login failed (password changed?)"),
    ],
    ids=["invalid-token", "login-failed"],
)
async def test_auth_errors_raise_auth_failed(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: AristonGalevoDevice,
    error: ConnectionException,
) -> None:
    """Test a refused login asks Home Assistant for a new login."""
    coordinator = make_coordinator(hass, config_entry, device, error)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_auth_error_while_polling_starts_reauth(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    api: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test an auth error in a poll starts the reauth flow, without a traceback."""
    api.async_get_properties.side_effect = ConnectionException("Invalid token")

    await init_integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]
    assert tracebacks(caplog) == []


async def test_server_error_while_polling_logs_no_traceback(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    api: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a failed poll makes entities unavailable and logs no traceback."""
    api.async_get_properties.side_effect = ConnectionException(500)

    await init_integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("climate.nimbus").state == STATE_UNAVAILABLE
    assert tracebacks(caplog) == []
