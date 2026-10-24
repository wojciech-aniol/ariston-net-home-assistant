"""Tests for the Ariston NET climate entity."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, call, patch

from ariston import AristonGalevoDevice
from ariston.const import PlantMode, ZoneMode
from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_HVAC_MODES,
    ATTR_PRESET_MODE,
    DATA_COMPONENT,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_ICON,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import PLANT_MODE_TEXTS, set_item

CLIMATE = "climate.nimbus"


@pytest.mark.parametrize(
    ("plant_mode_options", "expected_plant_mode"),
    [([0, 1, 2, 4, 5], PlantMode.OFF), ([0, 1, 2], PlantMode.SUMMER)],
    ids=["plant-off", "no-plant-off"],
)
async def test_hvac_mode_off_uses_plant_mode(
    hass: HomeAssistant,
    properties: dict[str, Any],
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    plant_mode_options: list[int],
    expected_plant_mode: PlantMode,
) -> None:
    """Test OFF is offered and set through the plant mode."""
    plant_mode = properties["items"][0]
    plant_mode["options"] = plant_mode_options
    plant_mode["optTexts"] = PLANT_MODE_TEXTS[: len(plant_mode_options)]
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert not device.is_zone_mode_options_contains_off(1)
    state = hass.states.get(CLIMATE)
    assert state.state == HVACMode.HEAT
    assert HVACMode.OFF in state.attributes[ATTR_HVAC_MODES]

    device.async_set_plant_mode = AsyncMock()
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )

    device.async_set_plant_mode.assert_awaited_once_with(expected_plant_mode)


async def setup_and_record_calls(
    hass: HomeAssistant, config_entry: MockConfigEntry, device: AristonGalevoDevice
) -> AsyncMock:
    """Set the entry up and record plant and zone mode calls in order."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    calls = AsyncMock()
    device.async_set_plant_mode = calls.plant_mode
    device.async_set_zone_mode = calls.zone_mode
    return calls


@pytest.mark.parametrize(
    ("hvac_mode", "plant_mode_options", "zone_mode_options", "expected_calls"),
    [
        (
            HVACMode.HEAT,
            [0, 1, 2, 4, 5],
            [2, 3],
            [
                call.plant_mode(PlantMode.HEATING_ONLY),
                call.zone_mode(ZoneMode.MANUAL, 1),
            ],
        ),
        (
            HVACMode.HEAT,
            [0, 1, 4, 5],
            [2, 3],
            [call.plant_mode(PlantMode.WINTER), call.zone_mode(ZoneMode.MANUAL, 1)],
        ),
        (
            HVACMode.HEAT,
            [0, 1, 2, 4, 5],
            [1, 2, 3],
            [
                call.plant_mode(PlantMode.HEATING_ONLY),
                call.zone_mode(ZoneMode.MANUAL_NIGHT, 1),
            ],
        ),
        (
            HVACMode.AUTO,
            [0, 1, 2, 4, 5],
            [2, 3],
            [
                call.plant_mode(PlantMode.HEATING_ONLY),
                call.zone_mode(ZoneMode.TIME_PROGRAM, 1),
            ],
        ),
        (
            HVACMode.AUTO,
            [0, 1, 4, 5],
            [2, 3],
            [
                call.plant_mode(PlantMode.WINTER),
                call.zone_mode(ZoneMode.TIME_PROGRAM, 1),
            ],
        ),
        (
            HVACMode.COOL,
            [0, 1, 2, 3, 5],
            [1, 2, 3],
            [
                call.plant_mode(PlantMode.COOLING),
                call.zone_mode(ZoneMode.MANUAL_NIGHT, 1),
            ],
        ),
    ],
    ids=[
        "heat",
        "heat-no-heating-only",
        "heat-manual-night",
        "auto",
        "auto-no-heating-only",
        "cool-manual-night",
    ],
)
async def test_hvac_mode_from_off_matches_device_options(
    hass: HomeAssistant,
    properties: dict[str, Any],
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    hvac_mode: HVACMode,
    plant_mode_options: list[int],
    zone_mode_options: list[int],
    expected_calls: list,
) -> None:
    """Test turning on from plant OFF picks modes from the device options."""
    set_item(
        properties, "PlantMode", value=PlantMode.OFF.value, options=plant_mode_options
    )
    set_item(
        properties, "ZoneMode", value=ZoneMode.OFF.value, options=zone_mode_options
    )
    calls = await setup_and_record_calls(hass, config_entry, device)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: hvac_mode},
        blocking=True,
    )

    assert calls.mock_calls == expected_calls


@pytest.mark.parametrize(
    ("plant_mode", "zone_mode", "preset", "expected_calls"),
    [
        (
            PlantMode.COOLING_ONLY,
            ZoneMode.TIME_PROGRAM,
            "Winter",
            [call.zone_mode(ZoneMode.MANUAL, 1), call.plant_mode(PlantMode.WINTER)],
        ),
        (
            PlantMode.WINTER,
            ZoneMode.MANUAL,
            "Off",
            [call.plant_mode(PlantMode.OFF), call.zone_mode(ZoneMode.OFF, 1)],
        ),
        (
            PlantMode.OFF,
            ZoneMode.OFF,
            "Winter",
            [call.plant_mode(PlantMode.WINTER), call.zone_mode(ZoneMode.MANUAL, 1)],
        ),
        (
            PlantMode.OFF,
            ZoneMode.OFF,
            "Summer",
            [call.plant_mode(PlantMode.SUMMER)],
        ),
        (
            PlantMode.SUMMER,
            ZoneMode.TIME_PROGRAM,
            "Heating only",
            [call.plant_mode(PlantMode.HEATING_ONLY)],
        ),
    ],
    ids=["leave-cooling", "off", "on-after-off", "summer-after-off", "zone-already-on"],
)
async def test_preset_sets_plant_and_zone_mode(
    hass: HomeAssistant,
    properties: dict[str, Any],
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    plant_mode: PlantMode,
    zone_mode: ZoneMode,
    preset: str,
    expected_calls: list,
) -> None:
    """Test a preset sets the plant mode and keeps the zone usable."""
    set_item(properties, "PlantMode", value=plant_mode.value)
    set_item(properties, "ZoneMode", value=zone_mode.value, options=[0, 2, 3])
    calls = await setup_and_record_calls(hass, config_entry, device)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_PRESET_MODE: preset},
        blocking=True,
    )

    assert calls.mock_calls == expected_calls


@pytest.mark.parametrize(
    ("plant_mode", "zone_mode", "pump_on", "heat_request", "expected_action"),
    [
        (PlantMode.WINTER, ZoneMode.MANUAL, True, True, HVACAction.HEATING),
        (PlantMode.WINTER, ZoneMode.MANUAL, True, False, HVACAction.IDLE),
        (PlantMode.WINTER, ZoneMode.MANUAL, False, True, HVACAction.IDLE),
        (PlantMode.WINTER, ZoneMode.OFF, True, True, HVACAction.OFF),
        (PlantMode.COOLING_ONLY, ZoneMode.MANUAL, True, False, HVACAction.COOLING),
        (PlantMode.SUMMER, ZoneMode.MANUAL, True, True, HVACAction.OFF),
    ],
    ids=["heating", "pump-for-dhw", "pump-off", "zone-off", "cooling", "summer"],
)
async def test_hvac_action_follows_zone(
    hass: HomeAssistant,
    properties: dict[str, Any],
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    plant_mode: PlantMode,
    zone_mode: ZoneMode,
    pump_on: bool,
    heat_request: bool,
    expected_action: HVACAction,
) -> None:
    """Test the action is off for an off zone and heats only on a zone request."""
    set_item(properties, "PlantMode", value=plant_mode.value)
    set_item(properties, "ZoneMode", value=zone_mode.value, options=[0, 2, 3])
    set_item(properties, "IsHeatingPumpOn", value=pump_on)
    set_item(properties, "ZoneHeatRequest", value=heat_request)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(CLIMATE).attributes[ATTR_HVAC_ACTION] == expected_action


async def test_missing_zone_mode_options_offer_only_off(
    hass: HomeAssistant,
    properties: dict[str, Any],
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test the entity works when the cloud sends no zone mode options."""
    zone_mode = next(item for item in properties["items"] if item["id"] == "ZoneMode")
    del zone_mode["options"]
    calls = await setup_and_record_calls(hass, config_entry, device)

    state = hass.states.get(CLIMATE)
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_HVAC_MODES] == [HVACMode.OFF]

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_PRESET_MODE: "Off"},
        blocking=True,
    )

    assert calls.mock_calls == [call.plant_mode(PlantMode.OFF)]


ALL_PLANT_MODES = [0, 1, 2, 3, 4, 5]
ALL_PLANT_MODE_TEXTS = [
    "Summer",
    "Winter",
    "Heating only",
    "Cooling",
    "Cooling only",
    "Off",
]

# The plant mode each HVAC mode sets, by the current plant mode. None: no change.
HVAC_MODE_PLANT_MODES: dict[HVACMode, dict[PlantMode, PlantMode | None]] = {
    HVACMode.OFF: dict.fromkeys(PlantMode, PlantMode.OFF),
    HVACMode.AUTO: {
        PlantMode.SUMMER: PlantMode.WINTER,
        PlantMode.WINTER: None,
        PlantMode.HEATING_ONLY: None,
        PlantMode.COOLING: None,
        PlantMode.COOLING_ONLY: PlantMode.HEATING_ONLY,
        PlantMode.OFF: PlantMode.HEATING_ONLY,
    },
    HVACMode.HEAT: {
        PlantMode.SUMMER: PlantMode.WINTER,
        PlantMode.WINTER: None,
        PlantMode.HEATING_ONLY: None,
        PlantMode.COOLING: PlantMode.WINTER,
        PlantMode.COOLING_ONLY: PlantMode.HEATING_ONLY,
        PlantMode.OFF: PlantMode.HEATING_ONLY,
    },
    HVACMode.COOL: dict.fromkeys(PlantMode, PlantMode.COOLING),
}

CURRENT_PLANT_MODES = [
    PlantMode.SUMMER,
    PlantMode.WINTER,
    PlantMode.HEATING_ONLY,
    PlantMode.COOLING,
    PlantMode.COOLING_ONLY,
    PlantMode.OFF,
]


def hvac_mode_calls(
    current: PlantMode, hvac_mode: HVACMode, manual_night: bool
) -> list:
    """Return the plant and zone mode calls expected for an HVAC mode.

    The zone starts off, and a mode the device already has is not set again.
    """
    expected = []
    plant_mode = HVAC_MODE_PLANT_MODES[hvac_mode][current]
    if plant_mode not in (None, current):
        expected.append(call.plant_mode(plant_mode))
    manual = ZoneMode.MANUAL_NIGHT if manual_night else ZoneMode.MANUAL
    zone_mode = {
        HVACMode.AUTO: ZoneMode.TIME_PROGRAM,
        HVACMode.HEAT: manual,
        HVACMode.COOL: manual,
    }.get(hvac_mode)
    if zone_mode is not None:
        expected.append(call.zone_mode(zone_mode, 1))
    return expected


@pytest.mark.parametrize("manual_night", [False, True], ids=["manual", "manual-night"])
@pytest.mark.parametrize("hvac_mode", list(HVAC_MODE_PLANT_MODES))
@pytest.mark.parametrize("current", CURRENT_PLANT_MODES, ids=lambda mode: mode.name)
async def test_hvac_mode_sets_plant_and_zone_mode(
    hass: HomeAssistant,
    properties: dict[str, Any],
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    current: PlantMode,
    hvac_mode: HVACMode,
    manual_night: bool,
) -> None:
    """Test each HVAC mode sets the plant and zone modes in order."""
    set_item(
        properties,
        "PlantMode",
        value=current.value,
        options=ALL_PLANT_MODES,
        optTexts=ALL_PLANT_MODE_TEXTS,
    )
    zone_mode_options = [0, 1, 2, 3] if manual_night else [0, 2, 3]
    set_item(
        properties, "ZoneMode", value=ZoneMode.OFF.value, options=zone_mode_options
    )
    calls = await setup_and_record_calls(hass, config_entry, device)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: hvac_mode},
        blocking=True,
    )

    assert calls.mock_calls == hvac_mode_calls(current, hvac_mode, manual_night)


async def test_hvac_mode_cool_sets_cooling_without_cooling_option(
    hass: HomeAssistant,
    properties: dict[str, Any],
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test COOL sets Cooling even when the device offers only Cooling only."""
    calls = await setup_and_record_calls(hass, config_entry, device)
    assert HVACMode.COOL in hass.states.get(CLIMATE).attributes[ATTR_HVAC_MODES]

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_HVAC_MODE: HVACMode.COOL},
        blocking=True,
    )

    # The zone is already manual.
    assert calls.mock_calls == [call.plant_mode(PlantMode.COOLING)]


@pytest.mark.parametrize(
    ("plant_mode", "zone_mode", "expected_mode"),
    [
        (PlantMode.WINTER, ZoneMode.MANUAL, HVACMode.HEAT),
        (PlantMode.HEATING_ONLY, ZoneMode.MANUAL_NIGHT, HVACMode.HEAT),
        (PlantMode.WINTER, ZoneMode.TIME_PROGRAM, HVACMode.AUTO),
        (PlantMode.WINTER, ZoneMode.OFF, HVACMode.OFF),
        (PlantMode.COOLING, ZoneMode.MANUAL, HVACMode.COOL),
        (PlantMode.COOLING_ONLY, ZoneMode.TIME_PROGRAM, HVACMode.AUTO),
        (PlantMode.COOLING_ONLY, ZoneMode.OFF, HVACMode.OFF),
        (PlantMode.SUMMER, ZoneMode.MANUAL, HVACMode.OFF),
        (PlantMode.OFF, ZoneMode.TIME_PROGRAM, HVACMode.OFF),
    ],
    ids=[
        "heat",
        "heat-manual-night",
        "auto-heating",
        "heating-zone-off",
        "cool",
        "auto-cooling",
        "cooling-zone-off",
        "summer",
        "plant-off",
    ],
)
async def test_hvac_mode_follows_plant_and_zone(
    hass: HomeAssistant,
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    plant_mode: PlantMode,
    zone_mode: ZoneMode,
    expected_mode: HVACMode,
) -> None:
    """Test the HVAC mode comes from the plant mode and the zone mode."""
    set_item(
        properties,
        "PlantMode",
        value=plant_mode.value,
        options=ALL_PLANT_MODES,
        optTexts=ALL_PLANT_MODE_TEXTS,
    )
    set_item(properties, "ZoneMode", value=zone_mode.value, options=[0, 1, 2, 3])
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(CLIMATE).state == expected_mode


@pytest.mark.parametrize(
    ("plant_mode", "pump_on", "expected_action"),
    [
        (PlantMode.COOLING_ONLY, False, HVACAction.IDLE),
        (PlantMode.COOLING, True, HVACAction.COOLING),
        (PlantMode.HEATING_ONLY, True, HVACAction.HEATING),
    ],
    ids=["cooling-idle", "cooling", "heating-only"],
)
async def test_hvac_action_follows_pump(
    hass: HomeAssistant,
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    plant_mode: PlantMode,
    pump_on: bool,
    expected_action: HVACAction,
) -> None:
    """Test the action is idle when neither the pump nor the flame runs."""
    set_item(
        properties,
        "PlantMode",
        value=plant_mode.value,
        options=ALL_PLANT_MODES,
        optTexts=ALL_PLANT_MODE_TEXTS,
    )
    set_item(properties, "IsHeatingPumpOn", value=pump_on)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(CLIMATE).attributes[ATTR_HVAC_ACTION] == expected_action


BASE_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TURN_OFF
    | ClimateEntityFeature.TURN_ON
)


@pytest.mark.parametrize(
    (
        "plant_mode_supported",
        "plant_mode_options",
        "zone_mode_options",
        "expected_modes",
        "expected_features",
    ),
    [
        (
            True,
            [0, 1, 2, 4, 5],
            [2, 3],
            [HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO, HVACMode.OFF],
            BASE_FEATURES | ClimateEntityFeature.PRESET_MODE,
        ),
        (
            True,
            [0, 1, 2, 5],
            [2, 3],
            [HVACMode.HEAT, HVACMode.AUTO, HVACMode.OFF],
            BASE_FEATURES | ClimateEntityFeature.PRESET_MODE,
        ),
        (
            True,
            [0, 1, 2, 5],
            [0, 3],
            [HVACMode.AUTO, HVACMode.OFF],
            BASE_FEATURES | ClimateEntityFeature.PRESET_MODE,
        ),
        (
            False,
            [0, 1, 2, 4, 5],
            [0, 2, 3],
            [HVACMode.HEAT, HVACMode.AUTO, HVACMode.OFF],
            BASE_FEATURES,
        ),
        (
            False,
            [0, 1, 2, 4, 5],
            [2, 3],
            [HVACMode.HEAT, HVACMode.AUTO],
            BASE_FEATURES,
        ),
    ],
    ids=[
        "cooling",
        "no-cooling",
        "no-manual",
        "no-plant-mode-zone-off",
        "no-plant-mode-no-zone-off",
    ],
)
async def test_hvac_modes_and_features_match_device(
    hass: HomeAssistant,
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    plant_mode_supported: bool,
    plant_mode_options: list[int],
    zone_mode_options: list[int],
    expected_modes: list[HVACMode],
    expected_features: ClimateEntityFeature,
) -> None:
    """Test the HVAC modes and features follow the plant and zone options."""
    set_item(
        properties,
        "PlantMode",
        options=plant_mode_options,
        optTexts=PLANT_MODE_TEXTS[: len(plant_mode_options)],
    )
    set_item(properties, "ZoneMode", options=zone_mode_options)
    # Only BSB devices have no plant mode; plan 04 tests the real BSB device.
    with patch.object(
        AristonGalevoDevice,
        "plant_mode_supported",
        new_callable=PropertyMock,
        return_value=plant_mode_supported,
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(CLIMATE)
    assert state.attributes[ATTR_HVAC_MODES] == expected_modes
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == expected_features


@pytest.mark.parametrize(
    ("plant_mode", "expected_icon"),
    [
        (PlantMode.WINTER, "mdi:radiator"),
        (PlantMode.HEATING_ONLY, "mdi:radiator"),
        (PlantMode.SUMMER, "mdi:radiator-off"),
        (PlantMode.COOLING_ONLY, "mdi:radiator-off"),
    ],
)
async def test_icon_shows_heat_mode(
    hass: HomeAssistant,
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    plant_mode: PlantMode,
    expected_icon: str,
) -> None:
    """Test the icon shows a radiator only when the plant heats."""
    set_item(properties, "PlantMode", value=plant_mode.value)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(CLIMATE).attributes[ATTR_ICON] == expected_icon


@pytest.mark.parametrize(
    ("plant_mode", "zone_mode", "zone_mode_options", "preset", "expected_calls"),
    [
        (
            PlantMode.WINTER,
            ZoneMode.MANUAL,
            [0, 2, 3],
            "Cooling only",
            [call.plant_mode(PlantMode.COOLING_ONLY)],
        ),
        (
            PlantMode.OFF,
            ZoneMode.OFF,
            [0, 2, 3],
            "Cooling only",
            [
                call.plant_mode(PlantMode.COOLING_ONLY),
                call.zone_mode(ZoneMode.MANUAL, 1),
            ],
        ),
        (
            PlantMode.OFF,
            ZoneMode.OFF,
            [0, 1, 2, 3],
            "Heating only",
            [
                call.plant_mode(PlantMode.HEATING_ONLY),
                call.zone_mode(ZoneMode.MANUAL_NIGHT, 1),
            ],
        ),
        (
            PlantMode.COOLING_ONLY,
            ZoneMode.TIME_PROGRAM,
            [0, 3],
            "Winter",
            [call.plant_mode(PlantMode.WINTER)],
        ),
        # Both modes are already set, so nothing is sent.
        (
            PlantMode.COOLING_ONLY,
            ZoneMode.MANUAL,
            [0, 2, 3],
            "Cooling only",
            [],
        ),
        (
            PlantMode.WINTER,
            ZoneMode.MANUAL,
            [2, 3],
            "Off",
            [call.plant_mode(PlantMode.OFF)],
        ),
    ],
    ids=[
        "by-option-value",
        "zone-on-for-cooling",
        "zone-on-manual-night",
        "leave-cooling-no-manual",
        "stay-in-cooling-only",
        "off-zone-without-off",
    ],
)
async def test_preset_sets_modes_from_options(
    hass: HomeAssistant,
    properties: dict[str, Any],
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    plant_mode: PlantMode,
    zone_mode: ZoneMode,
    zone_mode_options: list[int],
    preset: str,
    expected_calls: list,
) -> None:
    """Test a preset picks the plant mode by option value and fits the zone."""
    set_item(properties, "PlantMode", value=plant_mode.value)
    set_item(properties, "ZoneMode", value=zone_mode.value, options=zone_mode_options)
    calls = await setup_and_record_calls(hass, config_entry, device)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_PRESET_MODE: preset},
        blocking=True,
    )

    assert calls.mock_calls == expected_calls


async def test_preset_requests_refresh(
    hass: HomeAssistant,
    api: MagicMock,
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
) -> None:
    """Test a preset reads the device state again from the cloud."""
    await setup_and_record_calls(hass, config_entry, device)
    api.async_get_properties.reset_mock()

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_PRESET_MODE: "Summer"},
        blocking=True,
    )

    api.async_get_properties.assert_awaited_once()


async def test_set_temperature_sets_zone_comfort_temp(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device: AristonGalevoDevice,
) -> None:
    """Test the target temperature goes to the comfort temp of the zone."""
    device.async_set_comfort_temp = AsyncMock()

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: CLIMATE, ATTR_TEMPERATURE: 22.5},
        blocking=True,
    )

    device.async_set_comfort_temp.assert_awaited_once_with(22.5, 1)


async def test_set_temperature_without_temperature_raises(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test a call without a temperature fails.

    The service always sends one, so the entity is called directly.
    """
    entity = hass.data[DATA_COMPONENT].get_entity(CLIMATE)

    with pytest.raises(ServiceValidationError) as exc_info:
        await entity.async_set_temperature()

    assert exc_info.value.translation_key == "missing_temperature"


async def test_set_temperature_uses_zone_of_entity(
    hass: HomeAssistant,
    device: AristonGalevoDevice,
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    second_zone: int,
) -> None:
    """Test the climate of the second zone sets the temperature of that zone."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    device.async_set_comfort_temp = AsyncMock()

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: f"{CLIMATE}_{second_zone}", ATTR_TEMPERATURE: 19.5},
        blocking=True,
    )

    device.async_set_comfort_temp.assert_awaited_once_with(19.5, second_zone)
