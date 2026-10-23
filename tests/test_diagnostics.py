"""Tests for Ariston NET diagnostics."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from homeassistant.helpers.json import JSONEncoder
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from custom_components.ariston_net.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import GATEWAY


async def test_diagnostics_match_snapshot(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    init_full_integration: MockConfigEntry,
) -> None:
    """Test diagnostics hold all the cloud data of the device."""
    diagnostics = await async_get_config_entry_diagnostics(hass, init_full_integration)

    assert diagnostics == snapshot


async def test_diagnostics_hide_personal_data(
    hass: HomeAssistant,
    init_full_integration: MockConfigEntry,
) -> None:
    """Test diagnostics hold no password, username, gateway or serial number."""
    diagnostics = await async_get_config_entry_diagnostics(hass, init_full_integration)
    text = json.dumps(diagnostics, cls=JSONEncoder)

    for secret in ("test-password", "user@example.com", GATEWAY, "SN0001"):
        assert secret not in text
