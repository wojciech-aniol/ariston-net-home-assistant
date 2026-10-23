"""Fixtures for Ariston NET tests."""

from __future__ import annotations

from collections.abc import Generator
import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from ariston import AristonGalevoDevice
from ariston.const import ConsumptionTimeInterval, ConsumptionType
from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

from custom_components.ariston_net.const import DOMAIN

GATEWAY = "F0AD4E000001"

CLOUD_DEVICE: dict[str, Any] = {
    "gw": GATEWAY,
    "sys": 3,
    "name": "Nimbus",
    "sn": "SN0001",
    "fwVer": "1.2.3",
}

FEATURES: dict[str, Any] = {
    "zones": [{"num": 1, "name": "", "roomSens": True, "isHidden": False}],
    "hpSys": True,
    "hybridSys": False,
    "hasMetering": True,
    "hasBoiler": True,
    "dhwModeChangeable": True,
    "autoThermoReg": True,
}

PLANT_MODE_OPTIONS = [0, 1, 2, 4, 5]
PLANT_MODE_TEXTS = ["Summer", "Winter", "Heating only", "Cooling only", "Off"]

PROPERTIES: dict[str, Any] = {
    "items": [
        {
            "id": "PlantMode",
            "zone": 0,
            "value": 1,
            "options": PLANT_MODE_OPTIONS,
            "optTexts": PLANT_MODE_TEXTS,
        },
        {"id": "IsFlameOn", "zone": 0, "value": False},
        {"id": "IsHeatingPumpOn", "zone": 0, "value": True},
        {"id": "Holiday", "zone": 0, "value": False, "expiresOn": None},
        {"id": "OutsideTemp", "zone": 0, "value": 8.5, "max": 99, "unit": "°C"},
        {"id": "HeatingCircuitPressure", "zone": 0, "value": 1.6, "unit": "bar"},
        {"id": "ChFlowTemp", "zone": 0, "value": 35.0, "unit": "°C"},
        {"id": "ChFlowSetpointTemp", "zone": 0, "value": 36.0, "unit": "°C"},
        {
            "id": "DhwTemp",
            "zone": 0,
            "value": 50.0,
            "min": 40.0,
            "max": 65.0,
            "step": 1.0,
            "decimals": 0,
            "unit": "°C",
        },
        {"id": "DhwStorageTemperature", "zone": 0, "value": 47.5, "max": 99},
        {
            "id": "DhwMode",
            "zone": 0,
            "value": 1,
            "options": [1, 2],
            "optTexts": ["Time based", "Always active"],
        },
        {"id": "AutomaticThermoregulation", "zone": 0, "value": 1},
        {
            "id": "ZoneMode",
            "zone": 1,
            "value": 2,
            "options": [2, 3],
            "optTexts": ["Manual", "Programmed"],
        },
        {
            "id": "ZoneMeasuredTemp",
            "zone": 1,
            "value": 21.5,
            "decimals": 1,
            "unit": "°C",
        },
        {"id": "ZoneDesiredTemp", "zone": 1, "value": 21.0, "step": 0.5},
        {
            "id": "ZoneComfortTemp",
            "zone": 1,
            "value": 21.0,
            "min": 10.0,
            "max": 30.0,
            "step": 0.5,
        },
        {"id": "ZoneHeatRequest", "zone": 1, "value": True},
        {"id": "ZoneEconomyTemp", "zone": 1, "value": 18.0},
        {
            "id": "HeatingFlowTemp",
            "zone": 1,
            "value": 35.0,
            "min": 20.0,
            "max": 45.0,
            "step": 1.0,
            "decimals": 0,
            "unit": "°C",
        },
        {
            "id": "HeatingFlowOffset",
            "zone": 1,
            "value": 0.0,
            "min": -10.0,
            "max": 10.0,
            "step": 1.0,
            "decimals": 0,
            "unit": "°C",
        },
    ]
}

# Data a real device can send on top of the default set, so every GALEVO entity exists.
FULL_FEATURES: dict[str, Any] = {
    "hybridSys": True,
    "bufferTimeProgAvailable": True,
}

FULL_ITEMS: list[dict[str, Any]] = [
    {"id": "IsQuite", "zone": 0, "value": False},
    {
        "id": "HybridMode",
        "zone": 0,
        "value": 1,
        "options": [0, 1, 2],
        "optTexts": ["Economy", "Green", "Heat pump only"],
    },
    {
        "id": "BufferControlMode",
        "zone": 0,
        "value": 0,
        "options": [0, 1],
        "optTexts": ["Off", "Time program"],
    },
]

MENU_ITEMS: list[dict[str, Any]] = [
    {"id": 119, "value": 80.0, "unit": "%"},
    {"id": 124, "value": 30.5, "unit": "°C"},
]

BUS_ERRORS: list[dict[str, Any]] = [
    {
        "gw": GATEWAY,
        "timestamp": "2026-10-18T10:00:00",
        "fault": 902,
        "mult": 0,
        "code": "902",
        "pri": 1,
        "errDex": "Low water pressure",
        "res": False,
        "blk": False,
    }
]

CONSUMPTIONS_SEQUENCES: list[dict[str, Any]] = [
    {
        "k": consumption_type.value,
        "p": ConsumptionTimeInterval.LAST_DAY.value,
        "v": [1.5, 2.5],
    }
    for consumption_type in ConsumptionType
]

CONSUMPTIONS_SETTINGS: dict[str, Any] = {
    "currency": 2,
    "gasType": 0,
    "gasEnergyUnit": 0,
    "elecCost": 0.25,
    "gasCost": 0.1,
}

ENERGY_ACCOUNT: dict[str, Any] = {
    "LastMonth": [
        {"gas": 0, "elect": 120, "cool": 5},
        {"gas": 0, "elect": 40},
    ]
}


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return the snapshot fixture with the Home Assistant extension."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


@pytest.fixture
def features() -> dict[str, Any]:
    """Return the device features the fake cloud sends."""
    return copy.deepcopy(FEATURES)


@pytest.fixture
def properties() -> dict[str, Any]:
    """Return the device properties the fake cloud sends."""
    return copy.deepcopy(PROPERTIES)


@pytest.fixture
def api(features: dict[str, Any], properties: dict[str, Any]) -> MagicMock:
    """Return a fake Ariston cloud API."""
    api = MagicMock()
    api.async_get_features_for_device = AsyncMock(return_value=features)
    api.async_get_properties = AsyncMock(return_value=properties)
    api.async_get_menu_items = AsyncMock(return_value=[])
    api.async_get_bus_errors = AsyncMock(return_value=[])
    api.async_get_consumptions_sequences = AsyncMock(return_value=[])
    api.async_get_consumptions_settings = AsyncMock(return_value={})
    api.async_get_energy_account = AsyncMock(return_value={})
    api.async_set_property = AsyncMock()
    api.async_set_holiday = AsyncMock()
    return api


@pytest.fixture
def full_galevo(
    api: MagicMock,
    device: AristonGalevoDevice,
    features: dict[str, Any],
    properties: dict[str, Any],
) -> MagicMock:
    """Make the fake cloud send data for every GALEVO entity."""
    features.update(copy.deepcopy(FULL_FEATURES))
    properties["items"].extend(copy.deepcopy(FULL_ITEMS))
    device.attributes["hpmpSys"] = True
    api.async_get_menu_items.return_value = copy.deepcopy(MENU_ITEMS)
    api.async_get_bus_errors.return_value = copy.deepcopy(BUS_ERRORS)
    api.async_get_consumptions_sequences.return_value = copy.deepcopy(
        CONSUMPTIONS_SEQUENCES
    )
    api.async_get_consumptions_settings.return_value = copy.deepcopy(
        CONSUMPTIONS_SETTINGS
    )
    api.async_get_energy_account.return_value = copy.deepcopy(ENERGY_ACCOUNT)
    return api


@pytest.fixture
def device(api: MagicMock) -> AristonGalevoDevice:
    """Return a GALEVO device that talks to the fake cloud."""
    return AristonGalevoDevice(api, copy.deepcopy(CLOUD_DEVICE))


@pytest.fixture
def mock_ariston(device: AristonGalevoDevice) -> Generator[MagicMock]:
    """Patch the Ariston client used by the integration."""
    with patch("custom_components.ariston_net.Ariston", autospec=True) as ariston:
        client = ariston.return_value
        client.async_connect.return_value = True
        client.async_hello.return_value = device
        yield client


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a config entry for the fake device."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nimbus",
        unique_id=GATEWAY,
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "test-password",
            CONF_DEVICE: copy.deepcopy(CLOUD_DEVICE),
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_ariston: MagicMock
) -> MockConfigEntry:
    """Set up the integration with the fake device."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
