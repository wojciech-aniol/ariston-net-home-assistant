"""Tests for which entities Ariston NET creates and their shared parts."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from ariston_net_api import AristonGalevoDevice
from homeassistant.const import ATTR_FRIENDLY_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import EntityDescription
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import yaml

from custom_components.ariston_net.const import DOMAIN, EXTRA_STATE_ATTRIBUTE
from custom_components.ariston_net.sensor import (
    AristonSensor,
    AristonSensorEntityDescription,
)

from .conftest import CLOUD_DEVICE, GATEWAY, runtime_data, setup_integration

FLAME = "binary_sensor.nimbus_flame"
CH_RETURN_TEMP = "sensor.nimbus_ariston_net_ch_return_temp"

INTEGRATION_DIR = Path(__file__).parents[1] / "custom_components" / DOMAIN
# Platforms whose entities get names from translations.
NAMED_PLATFORMS = ["binary_sensor", "number", "select", "switch"]


def descriptions(platform: str) -> list[EntityDescription]:
    """Return the entity descriptions of a platform."""
    module = importlib.import_module(f"custom_components.ariston_net.{platform}")
    return getattr(module, f"ARISTON_{platform.upper()}_TYPES")


@pytest.mark.parametrize(("has_flame", "expected"), [(True, True), (False, False)])
async def test_flame_sensor_needs_flame_value(
    hass: HomeAssistant,
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    has_flame: bool,
    expected: bool,
) -> None:
    """Test the flame sensor is skipped when the device has no flame value."""
    if not has_flame:
        properties["items"] = [
            item for item in properties["items"] if item["id"] != "IsFlameOn"
        ]

    await setup_integration(hass, config_entry)

    assert (hass.states.get(FLAME) is not None) is expected


@pytest.mark.parametrize(
    ("menu_items", "expected"),
    [([{"id": 124, "value": 31.5, "unit": "°C"}], True), ([], False)],
)
async def test_ch_return_temp_needs_menu_value(
    hass: HomeAssistant,
    api: MagicMock,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    menu_items: list[dict[str, Any]],
    expected: bool,
) -> None:
    """Test the CH return temperature is skipped without a menu value."""
    api.menu_items_request.return_value = menu_items

    await setup_integration(hass, config_entry)

    state = hass.states.get(CH_RETURN_TEMP)
    assert (state is not None) is expected
    if expected:
        assert state.state == "31.5"


@pytest.mark.parametrize(
    ("whe_type", "whe_model_type", "expected_model"),
    [
        (None, None, "GALEVO"),
        (1, None, "GALEVO Evo"),
        (1, 3, "GALEVO Evo | Model 3"),
    ],
    ids=["no-whe-type", "whe-type", "whe-model"],
)
async def test_device_model_shows_whe_type(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    whe_type: int | None,
    whe_model_type: int | None,
    expected_model: str,
) -> None:
    """Test the device model adds the WHE type and model number when known."""
    if whe_type is not None:
        device.attributes["wheType"] = whe_type
    if whe_model_type is not None:
        device.attributes["wheModelType"] = whe_model_type

    await setup_integration(hass, config_entry)

    (device_entry,) = dr.async_entries_for_config_entry(
        device_registry, config_entry.entry_id
    )
    assert device_entry.model == expected_model


async def test_extra_state_without_method_is_skipped(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test an extra state with no device method adds no attribute.

    No description has one today, so the entity is built directly.
    """
    coordinator = runtime_data(hass).coordinator
    description = AristonSensorEntityDescription(
        key="no_method",
        get_native_value=lambda entity: 1,
        extra_states=[{EXTRA_STATE_ATTRIBUTE: "no_method"}],
    )

    sensor = AristonSensor(coordinator, description)

    assert sensor.extra_state_attributes == {}


# Entity ID, unique ID, name before has_entity_name, and new friendly name.
OLDER_INSTALL_ENTITIES = [
    (
        "binary_sensor.nimbus_ariston_net_holiday_mode",
        f"{GATEWAY}-Ariston NET holiday mode",
        "Ariston NET holiday mode",
        "Nimbus Holiday mode",
    ),
    (
        "binary_sensor.nimbus_ariston_net_is_heating_pump_on",
        f"{GATEWAY}-Ariston NET is heating pump on",
        "Ariston NET is heating pump on",
        "Nimbus Heat pump",
    ),
    ("climate.nimbus", f"{GATEWAY}_1", "Nimbus", "Nimbus"),
    ("climate.nimbus_2", f"{GATEWAY}_2", "Nimbus", "Nimbus"),
    (
        "number.nimbus_ariston_net_elec_cost",
        f"{GATEWAY}-Ariston NET elec cost",
        "Ariston NET elec cost",
        "Nimbus Electricity cost",
    ),
    (
        "number.nimbus_ariston_net_heating_flow_temperature_2",
        f"{GATEWAY}-Ariston NET heating flow temperature 2-2",
        "Ariston NET heating flow temperature 2",
        "Nimbus Zone 2 heating flow temperature",
    ),
    (
        "select.nimbus_ariston_net_plant_mode",
        f"{GATEWAY}-Ariston NET plant mode",
        "Ariston NET plant mode",
        "Nimbus Plant mode",
    ),
    (
        "select.nimbus_ariston_net_currency",
        f"{GATEWAY}-Ariston NET currency",
        "Ariston NET currency",
        "Nimbus Currency",
    ),
    (
        "switch.nimbus_ariston_net_automatic_thermoregulation",
        f"{GATEWAY}-Ariston NET automatic thermoregulation",
        "Ariston NET automatic thermoregulation",
        "Nimbus Automatic thermoregulation",
    ),
    (
        "switch.nimbus_ariston_net_is_quiet",
        f"{GATEWAY}-Ariston NET is quiet",
        "Ariston NET is quiet",
        "Nimbus Quiet mode",
    ),
    ("water_heater.nimbus", f"{GATEWAY}-water_heater", "Nimbus", "Nimbus"),
]


@pytest.mark.parametrize(
    ("entity_id", "unique_id", "old_name", "friendly_name"), OLDER_INSTALL_ENTITIES
)
@pytest.mark.usefixtures("full_galevo", "second_zone")
async def test_existing_entity_keeps_ids_with_new_name(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    entity_id: str,
    unique_id: str,
    old_name: str,
    friendly_name: str,
) -> None:
    """Test an entity of an older install keeps its IDs and shows the new name."""
    device_entry = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, CLOUD_DEVICE["sn"])},
        name=CLOUD_DEVICE["name"],
    )
    domain, object_id = entity_id.split(".")
    entity_registry.async_get_or_create(
        domain,
        DOMAIN,
        unique_id,
        suggested_object_id=object_id,
        config_entry=config_entry,
        device_id=device_entry.id,
        has_entity_name=False,
        original_name=old_name,
    )

    await setup_integration(hass, config_entry)

    assert entity_registry.async_get_entity_id(domain, DOMAIN, unique_id) == entity_id
    assert hass.states.get(entity_id).attributes[ATTR_FRIENDLY_NAME] == friendly_name


async def test_zone_number_without_zone_number_shows_zone_0(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    features: dict[str, Any],
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test a zone the cloud sends with no number keeps its unique ID and shows zone 0."""
    del features["zones"][0]["num"]
    for item in properties["items"]:
        if item["zone"] == 1:
            item["zone"] = 0

    await setup_integration(hass, config_entry)

    entity_id = entity_registry.async_get_entity_id(
        "number", DOMAIN, f"{GATEWAY}-Ariston NET heating flow temperature"
    )
    state = hass.states.get(entity_id)
    assert state.attributes[ATTR_FRIENDLY_NAME] == (
        "Nimbus Zone 0 heating flow temperature"
    )


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("binary_sensor", 0),
        ("sensor", 0),
        ("climate", 1),
        ("number", 1),
        ("select", 1),
        ("switch", 1),
        ("water_heater", 1),
    ],
)
def test_platform_parallel_updates(platform: str, expected: int) -> None:
    """Test read-only platforms run in parallel and writes go one at a time."""
    module = importlib.import_module(f"custom_components.ariston_net.{platform}")

    assert expected == module.PARALLEL_UPDATES


@pytest.mark.parametrize(
    "path", ["strings.json", "translations/en.json", "translations/pl.json"]
)
@pytest.mark.parametrize("platform", NAMED_PLATFORMS)
def test_translation_keys_have_names(platform: str, path: str) -> None:
    """Test each translation key of a platform has a name, and no name is unused."""
    names = json.loads((INTEGRATION_DIR / path).read_text())["entity"][platform]

    assert set(names) == {
        description.translation_key for description in descriptions(platform)
    }
    assert all(name["name"] for name in names.values())


@pytest.mark.parametrize(
    "path", ["strings.json", "translations/en.json", "translations/pl.json"]
)
def test_zone_names_have_zone_placeholder(path: str) -> None:
    """Test zone numbers have the zone in their name, so zones get different names."""
    names = json.loads((INTEGRATION_DIR / path).read_text())["entity"]["number"]

    for description in descriptions("number"):
        if description.zone:
            assert "{zone}" in names[description.translation_key]["name"]


async def test_entity_name_follows_ha_language(
    hass: HomeAssistant, mock_ariston: MagicMock, config_entry: MockConfigEntry
) -> None:
    """Test new entities get names and entity IDs in the language of Home Assistant."""
    hass.config.language = "pl"

    await setup_integration(hass, config_entry)

    state = hass.states.get("select.nimbus_tryb_instalacji")
    assert state.attributes[ATTR_FRIENDLY_NAME] == "Nimbus Tryb instalacji"


@pytest.mark.parametrize("platform", [*NAMED_PLATFORMS, "climate", "water_heater"])
def test_translation_keys_have_icons(platform: str) -> None:
    """Test each translation key of a platform has an icon, and no icon is unused."""
    icons = json.loads((INTEGRATION_DIR / "icons.json").read_text())["entity"]

    assert set(icons[platform]) == {
        description.translation_key for description in descriptions(platform)
    }


def test_services_have_icons() -> None:
    """Test each service has an icon, and no icon is unused."""
    icons = json.loads((INTEGRATION_DIR / "icons.json").read_text())["services"]
    services = yaml.safe_load((INTEGRATION_DIR / "services.yaml").read_text())

    assert set(icons) == set(services)
