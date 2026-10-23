"""Tests for the Ariston NET config flow."""

from __future__ import annotations

from collections.abc import Generator
import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from ariston.const import ARISTON_API_URL, ARISTON_USER_AGENT
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
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

from .conftest import CLOUD_DEVICE, GATEWAY

USER_INPUT: dict[str, Any] = {
    CONF_USERNAME: "new@example.com",
    CONF_PASSWORD: "new-password",
    API_URL_SETTING: ARISTON_API_URL,
    API_USER_AGENT: ARISTON_USER_AGENT,
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
        "new@example.com", "new-password", ARISTON_API_URL, ARISTON_USER_AGENT
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


async def test_user_step_exception_shows_unknown(
    hass: HomeAssistant, flow_ariston: MagicMock
) -> None:
    """Test any login exception shows the unknown error."""
    flow_ariston.async_connect.side_effect = ConnectionError

    result = await start_user_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_user_step_no_devices_shows_error(
    hass: HomeAssistant, flow_ariston: MagicMock
) -> None:
    """Test an account with no devices shows the form again with an error."""
    flow_ariston.async_discover.return_value = []

    result = await start_user_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "no device found"}


async def test_user_step_existing_entry_updated_and_aborts(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    flow_ariston: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test adding a known device again saves the new login and reloads it."""
    result = await start_user_flow(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert dict(config_entry.data) == USER_INPUT | {CONF_DEVICE: CLOUD_DEVICE}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    mock_setup_entry.assert_awaited_once()


async def test_reauth_flow_saves_new_login(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    flow_ariston: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test the reauth flow asks for the full login form and saves it."""
    result = await config_entry.start_reauth_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_PASSWORD] == "new-password"


async def test_options_flow_shows_defaults(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test the options form shows the default of each option."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)

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
    hass: HomeAssistant, init_integration: MockConfigEntry, api: MagicMock
) -> None:
    """Test the options flow saves all five options and reloads the entry."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    api.async_get_consumptions_sequences.reset_mock()

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=OPTIONS
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == OPTIONS
    api.async_get_consumptions_sequences.assert_not_called()
