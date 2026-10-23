"""Tests for Ariston NET diagnostics."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from homeassistant.helpers.json import JSONEncoder
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import GATEWAY


async def test_diagnostics(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test diagnostics hold the cloud data but no personal data."""
    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)
    text = json.dumps(diagnostics, cls=JSONEncoder)

    for secret in ("test-password", "user@example.com", GATEWAY, "SN0001"):
        assert secret not in text

    device = diagnostics["device"]
    assert device["system_type"] == "GALEVO"
    assert device["features"]["hpSys"] is True
    assert any(item["id"] == "PlantMode" for item in device["data"]["items"])
    assert diagnostics["coordinators"]["coordinator"]["last_update_success"]
