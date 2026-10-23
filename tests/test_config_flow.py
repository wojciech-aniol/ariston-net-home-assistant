"""Tests for the Ariston NET config flow."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import (
    BUS_ERRORS_SCAN_INTERVAL,
    ENABLE_BUS_ERRORS,
    ENABLE_ENERGY,
    ENERGY_SCAN_INTERVAL,
)


async def test_options_flow(
    hass: HomeAssistant, init_integration: MockConfigEntry, api: MagicMock
) -> None:
    """Test the options turn off energy polling and keep the intervals."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert {str(key) for key in result["data_schema"].schema} == {
        CONF_SCAN_INTERVAL,
        ENABLE_ENERGY,
        ENERGY_SCAN_INTERVAL,
        ENABLE_BUS_ERRORS,
        BUS_ERRORS_SCAN_INTERVAL,
    }

    api.async_get_consumptions_sequences.reset_mock()
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_SCAN_INTERVAL: 180,
            ENABLE_ENERGY: False,
            ENERGY_SCAN_INTERVAL: 1440,
            ENABLE_BUS_ERRORS: True,
            BUS_ERRORS_SCAN_INTERVAL: 900,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options[ENABLE_ENERGY] is False
    assert init_integration.options[BUS_ERRORS_SCAN_INTERVAL] == 900
    api.async_get_consumptions_sequences.assert_not_called()
