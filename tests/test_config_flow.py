"""Tests for the Ariston NET config flow."""

from __future__ import annotations

from collections.abc import Generator
import copy
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
from ariston.ariston_api import ConnectionException
from ariston.const import ARISTON_API_URL, ARISTON_USER_AGENT
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import (
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import (
    API_URL_SETTING,
    API_USER_AGENT,
    BUS_ERRORS_SCAN_INTERVAL,
    DOMAIN,
    ENABLE_BUS_ERRORS,
    ENABLE_ENERGY,
    ENERGY_SCAN_INTERVAL,
)

from .conftest import CLOUD_DEVICE, GATEWAY, tracebacks

USER_INPUT: dict[str, Any] = {
    CONF_USERNAME: "new@example.com",
    CONF_PASSWORD: "new-password",
    API_URL_SETTING: "https://cloud.example.com/api/v2/",
    API_USER_AGENT: "TestAgent/1.0",
}

OTHER_DEVICE: dict[str, Any] = {
    "gw": "F0AD4E000002",
    "sys": 3,
    "name": "Garage",
    "sn": "SN0002",
}

OPTIONS: dict[str, Any] = {
    CONF_SCAN_INTERVAL: 300,
    ENABLE_ENERGY: False,
    ENERGY_SCAN_INTERVAL: 1440,
    ENABLE_BUS_ERRORS: False,
    BUS_ERRORS_SCAN_INTERVAL: 900,
}


@pytest.fixture
def flow_ariston() -> Generator[MagicMock]:
    """Patch the Ariston client used by the config flow."""
    with patch(
        "custom_components.ariston_net.config_flow.Ariston", autospec=True
    ) as ariston:
        client = ariston.return_value
        client.async_connect.return_value = True
        client.async_discover.return_value = [copy.deepcopy(CLOUD_DEVICE)]
        yield client


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip the entry setup that follows the flow."""
    with patch(
        "custom_components.ariston_net.async_setup_entry", return_value=True
    ) as setup_entry:
        yield setup_entry


async def start_user_flow(hass: HomeAssistant) -> dict[str, Any]:
    """Start the user flow and send the login form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )


def schema_defaults(result: dict[str, Any]) -> dict[str, Any]:
    """Return the default value of each field in a form."""
    return {str(key): key.default() for key in result["data_schema"].schema}


async def test_user_step_shows_form(hass: HomeAssistant) -> None:
    """Test the flow starts with the login form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]


async def test_user_step_one_device_creates_entry(
    hass: HomeAssistant, flow_ariston: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """Test one device on the account creates the entry at once."""
    result = await start_user_flow(hass)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Nimbus"
    assert result["result"].unique_id == GATEWAY
    assert result["data"] == USER_INPUT | {CONF_DEVICE: CLOUD_DEVICE}
    flow_ariston.async_connect.assert_awaited_once_with(
        "new@example.com",
        "new-password",
        "https://cloud.example.com/api/v2/",
        "TestAgent/1.0",
    )
    mock_setup_entry.assert_awaited_once()


async def test_user_step_many_devices_creates_selected_entry(
    hass: HomeAssistant, flow_ariston: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """Test several devices go to the select step and the chosen one is added."""
    flow_ariston.async_discover.return_value = [
        copy.deepcopy(CLOUD_DEVICE),
        copy.deepcopy(OTHER_DEVICE),
    ]

    result = await start_user_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select"
    assert result["data_schema"].schema["select_device"].container == [
        "Nimbus - SN0001",
        "Garage - SN0002",
    ]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"select_device": "Garage - SN0002"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Garage"
    assert result["result"].unique_id == "F0AD4E000002"
    assert result["data"][CONF_DEVICE] == OTHER_DEVICE


async def test_user_step_refused_login_shows_invalid_auth(
    hass: HomeAssistant, flow_ariston: MagicMock
) -> None:
    """Test a refused login shows the invalid auth error."""
    flow_ariston.async_connect.return_value = False

    result = await start_user_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}
    flow_ariston.async_discover.assert_not_called()


def login_error(cause: Exception) -> ConnectionException:
    """Return the error a login raises: an empty one that wraps the cause."""
    error = ConnectionException()
    error.__cause__ = cause
    return error


@pytest.mark.parametrize(
    ("method", "error", "key"),
    [
        ("async_connect", login_error(ConnectionException(401)), "invalid_auth"),
        ("async_connect", login_error(ConnectionException(500)), "cannot_connect"),
        ("async_connect", login_error(aiohttp.ClientError()), "cannot_connect"),
        ("async_discover", ConnectionException(500), "cannot_connect"),
        ("async_discover", TimeoutError(), "cannot_connect"),
        ("async_connect", ValueError(), "unknown"),
    ],
    ids=[
        "login-401",
        "login-500",
        "login-network",
        "discover-500",
        "discover-timeout",
        "unexpected",
    ],
)
async def test_user_step_error_shows_error(
    hass: HomeAssistant,
    flow_ariston: MagicMock,
    mock_setup_entry: AsyncMock,
    method: str,
    error: Exception,
    key: str,
) -> None:
    """Test each login error shows its error, and the flow can go on after it."""
    getattr(flow_ariston, method).side_effect = error

    result = await start_user_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": key}

    getattr(flow_ariston, method).side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_step_unexpected_error_is_logged(
    hass: HomeAssistant,
    flow_ariston: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test only an unexpected error is logged with a traceback."""
    flow_ariston.async_connect.side_effect = ValueError

    await start_user_flow(hass)

    assert tracebacks(caplog) == ["Unexpected error while logging in to Ariston"]


async def test_user_step_no_devices_aborts(
    hass: HomeAssistant, flow_ariston: MagicMock
) -> None:
    """Test an account with no devices ends the flow."""
    flow_ariston.async_discover.return_value = []

    result = await start_user_flow(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_step_existing_entry_updated_and_aborts(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    flow_ariston: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test adding a known device again saves the new login and reloads it."""
    await hass.config_entries.async_setup(config_entry.entry_id)

    result = await start_user_flow(hass)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert dict(config_entry.data) == USER_INPUT | {CONF_DEVICE: CLOUD_DEVICE}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert mock_setup_entry.await_count == 2


async def start_reauth(
    hass: HomeAssistant, entry: MockConfigEntry, password: str = "new-password"
) -> dict[str, Any]:
    """Start the reauth flow and send a password."""
    result = await entry.start_reauth_flow(hass)
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_PASSWORD: password}
    )


async def test_reauth_flow_asks_only_for_password(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Test the reauth form has only the password and names the account."""
    result = await config_entry.start_reauth_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert list(result["data_schema"].schema) == [CONF_PASSWORD]
    assert result["description_placeholders"]["username"] == "user@example.com"


async def test_reauth_flow_saves_new_password(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    flow_ariston: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test reauth logs in with the saved account and saves the new password."""
    old_data = dict(config_entry.data)

    result = await start_reauth(hass, config_entry)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert dict(config_entry.data) == old_data | {CONF_PASSWORD: "new-password"}
    flow_ariston.async_connect.assert_awaited_once_with(
        "user@example.com", "new-password", ARISTON_API_URL, ARISTON_USER_AGENT
    )
    mock_setup_entry.assert_awaited_once()


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (login_error(ConnectionException(401)), "invalid_auth"),
        (login_error(ConnectionException(500)), "cannot_connect"),
    ],
    ids=["login-401", "login-500"],
)
async def test_reauth_flow_error_shows_error(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    flow_ariston: MagicMock,
    error: ConnectionException,
    key: str,
) -> None:
    """Test a failed login keeps the reauth form with its error."""
    flow_ariston.async_connect.side_effect = error

    result = await start_reauth(hass, config_entry)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"] == {"base": key}
    assert config_entry.data[CONF_PASSWORD] == "test-password"


async def test_reauth_flow_other_account_aborts(
    hass: HomeAssistant, config_entry: MockConfigEntry, flow_ariston: MagicMock
) -> None:
    """Test reauth aborts when the account does not have the entry's device."""
    flow_ariston.async_discover.return_value = [copy.deepcopy(OTHER_DEVICE)]

    result = await start_reauth(hass, config_entry)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
    assert config_entry.data[CONF_PASSWORD] == "test-password"


async def test_options_flow_shows_defaults(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_setup_entry: AsyncMock
) -> None:
    """Test the options form shows the default of each option."""
    await hass.config_entries.async_setup(config_entry.entry_id)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert schema_defaults(result) == {
        CONF_SCAN_INTERVAL: 180,
        ENABLE_ENERGY: True,
        ENERGY_SCAN_INTERVAL: 60,
        ENABLE_BUS_ERRORS: True,
        BUS_ERRORS_SCAN_INTERVAL: 600,
    }


async def test_options_flow_shows_saved_options(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_setup_entry: AsyncMock
) -> None:
    """Test the options form keeps all five saved options."""
    hass.config_entries.async_update_entry(config_entry, options=OPTIONS)
    await hass.config_entries.async_setup(config_entry.entry_id)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert schema_defaults(result) == OPTIONS


async def test_options_flow_saves_options(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the options flow saves all five options and reloads the entry."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=OPTIONS
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == OPTIONS
    data = init_integration.runtime_data
    assert data.coordinator.update_interval == timedelta(seconds=300)
    assert data.energy_coordinator is None
    assert data.bus_errors_coordinator is None


@pytest.mark.parametrize(
    ("option", "minimum"),
    [
        (CONF_SCAN_INTERVAL, 60),
        (ENERGY_SCAN_INTERVAL, 15),
        (BUS_ERRORS_SCAN_INTERVAL, 60),
    ],
)
async def test_options_flow_accepts_minimum(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
    option: str,
    minimum: int,
) -> None:
    """Test each interval option takes its minimum."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=OPTIONS | {option: minimum}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[option] == minimum


@pytest.mark.parametrize(
    ("option", "minimum", "message"),
    [
        (CONF_SCAN_INTERVAL, 60, "Use at least 60 seconds"),
        (ENERGY_SCAN_INTERVAL, 15, "Use at least 15 minutes"),
        (BUS_ERRORS_SCAN_INTERVAL, 60, "Use at least 60 seconds"),
    ],
)
async def test_options_flow_refuses_below_minimum(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
    option: str,
    minimum: int,
    message: str,
) -> None:
    """Test an interval below its minimum shows an error on that field only."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    with pytest.raises(InvalidData) as exc_info:
        await hass.config_entries.options.async_configure(
            result["flow_id"], user_input=OPTIONS | {option: minimum - 1}
        )

    assert list(exc_info.value.schema_errors) == [option]
    assert exc_info.value.schema_errors[option].startswith(message)
    assert config_entry.options == {}


async def test_user_step_reloads_entry_that_failed_on_old_login(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_ariston: MagicMock,
    flow_ariston: MagicMock,
) -> None:
    """Test adding the device again with a new login sets up the failed entry."""
    mock_ariston.async_connect.return_value = False
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR

    mock_ariston.async_connect.return_value = True
    result = await start_user_flow(hass)
    await hass.async_block_till_done()

    assert result["reason"] == "already_configured"
    assert config_entry.state is ConfigEntryState.LOADED


async def test_reauth_of_loaded_entry_reloads_once(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_ariston: MagicMock,
    flow_ariston: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test reauth of a loaded entry reloads it once, with no usage warning."""
    mock_ariston.async_connect.reset_mock()

    result = await start_reauth(hass, init_integration)
    await hass.async_block_till_done()

    assert result["reason"] == "reauth_successful"
    assert init_integration.state is ConfigEntryState.LOADED
    mock_ariston.async_connect.assert_awaited_once()
    assert "update listener" not in caplog.text


async def test_options_flow_raises_old_interval_to_minimum(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_setup_entry: AsyncMock
) -> None:
    """Test the form offers the minimum when a saved interval is below it."""
    hass.config_entries.async_update_entry(
        config_entry, options=OPTIONS | {CONF_SCAN_INTERVAL: 30}
    )
    await hass.config_entries.async_setup(config_entry.entry_id)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert schema_defaults(result)[CONF_SCAN_INTERVAL] == 60
