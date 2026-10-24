"""Fixtures for Ariston NET tests."""

from __future__ import annotations

from collections.abc import Generator
import copy
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from ariston import AristonGalevoDevice
from ariston.ariston_api import ConnectionException
from homeassistant.const import CONF_DEVICE, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

from custom_components.ariston_net.const import DOMAIN
from custom_components.ariston_net.coordinator import AristonData
from custom_components.ariston_net.menu_items import BLOCKED_MENU_IDS

GATEWAY = "F0AD4E000001"
BLOCKED_IDS = ",".join(str(item_id) for item_id in BLOCKED_MENU_IDS)

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
            "value": 22.0,
            "min": 10.0,
            "max": 30.0,
            "step": 0.5,
        },
        {"id": "ZoneHeatRequest", "zone": 1, "value": True},
        {"id": "ZoneEconomyTemp", "zone": 1, "value": 18.0},
        {
            "id": "HeatingFlowTemp",
            "zone": 1,
            "value": 38.0,
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
    {"id": 348, "value": 27.0, "unit": "°C"},
    {"id": 349, "value": 25.0, "unit": "°C"},
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

# Plain numbers, not the library enums, so a new library version cannot change
# the data. Each consumption type gets its own values.
CONSUMPTION_TYPES = (1, 2, 3, 7, 8, 9, 10, 20, 21)
LAST_DAY = 1

CONSUMPTIONS_SEQUENCES: list[dict[str, Any]] = [
    {"k": k, "p": LAST_DAY, "v": [k + 0.25, k + 0.5]} for k in CONSUMPTION_TYPES
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
        {"gas": 30, "elect": 120, "cool": 5},
        {"gas": 12, "elect": 40},
    ]
}


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the config entry."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def runtime_data(hass: HomeAssistant) -> AristonData:
    """Return the runtime data of the fake device's entry."""
    entry = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, GATEWAY)
    return entry.runtime_data


async def refresh_energy(hass: HomeAssistant, api: MagicMock) -> None:
    """Send new energy data, so the total energy sensors get a value."""
    api.async_get_consumptions_sequences.return_value = [
        sequence | {"v": [*sequence["v"], sequence["v"][-1] + 1]}
        for sequence in api.async_get_consumptions_sequences.return_value
    ]
    await runtime_data(hass).energy_coordinator.async_refresh()
    await hass.async_block_till_done()


def tracebacks(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Return the messages logged with a traceback, apart from debug ones."""
    return [
        record.getMessage()
        for record in caplog.records
        if record.exc_info and record.levelno > logging.DEBUG
    ]


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return the snapshot fixture with the Home Assistant extension.

    The plugin has the same fixture, but the syrupy one wins over it.
    """
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
    # The integration sends two menu items requests through _async_get: the
    # polled one, and one at setup for the blocked IDs (refused like in the cloud).
    api.menu_items_request = AsyncMock(return_value=[])
    api.blocked_menu_items_request = AsyncMock(side_effect=ConnectionException(500))

    async def async_get(url: str) -> Any:
        if f"menuItems={BLOCKED_IDS}" in url:
            return await api.blocked_menu_items_request(url)
        return await api.menu_items_request(url)

    api._async_get = AsyncMock(side_effect=async_get)
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
    api.menu_items_request.return_value = copy.deepcopy(MENU_ITEMS)
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
def second_zone(features: dict[str, Any], properties: dict[str, Any]) -> int:
    """Add a second zone with its own values and return its number."""
    zone = 2
    features["zones"].append(
        {"num": zone, "name": "", "roomSens": True, "isHidden": False}
    )
    zone_items = [item for item in properties["items"] if item["zone"] == 1]
    for item in copy.deepcopy(zone_items):
        item["zone"] = zone
        if isinstance(item["value"], float):
            item["value"] += 1
        properties["items"].append(item)
    return zone


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
async def init_full_integration(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_ariston: MagicMock,
    full_galevo: MagicMock,
) -> MockConfigEntry:
    """Set up the integration with the full GALEVO data."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_ariston: MagicMock
) -> MockConfigEntry:
    """Set up the integration with the fake device."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
