"""Tests for the handling of Ariston cloud errors."""

from __future__ import annotations

import importlib
import inspect
from typing import Any
from unittest.mock import MagicMock

import aiohttp
from ariston_net_api.ariston_api import ConnectionException
from ariston_net_api.const import PlantMode, ZoneMode
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.water_heater import (
    ATTR_OPERATION_MODE,
    DOMAIN as WATER_HEATER_DOMAIN,
    SERVICE_SET_OPERATION_MODE,
)
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net import PLATFORMS
from custom_components.ariston_net.const import DOMAIN
from custom_components.ariston_net.entity import AristonEntity
from custom_components.ariston_net.errors import (
    CloudErrorKind,
    classify_error,
    describe_error,
)

from .conftest import set_item, setup_integration, tracebacks


def login_error(cause: Exception | None) -> ConnectionException:
    """Return the error a login raises: an empty one that wraps the cause."""
    error = ConnectionException()
    error.__cause__ = cause
    return error


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (ConnectionException("Invalid token"), CloudErrorKind.AUTH),
        (ConnectionException("Login failed (password changed?)"), CloudErrorKind.AUTH),
        (login_error(ConnectionException(401)), CloudErrorKind.AUTH),
        (login_error(ConnectionException(403)), CloudErrorKind.AUTH),
        (login_error(ConnectionException("Invalid token")), CloudErrorKind.AUTH),
        (ConnectionException(429, b"body"), CloudErrorKind.RATE_LIMIT),
        (login_error(ConnectionException(429)), CloudErrorKind.RATE_LIMIT),
        (ConnectionException(500), CloudErrorKind.SERVER),
        (login_error(ConnectionException(503)), CloudErrorKind.SERVER),
        (ConnectionException(400), CloudErrorKind.OTHER),
        (ConnectionException("429"), CloudErrorKind.OTHER),
        (ConnectionException(), CloudErrorKind.OTHER),
        (login_error(aiohttp.ClientError()), CloudErrorKind.OTHER),
        (login_error(KeyError("token")), CloudErrorKind.OTHER),
        (ConnectionException(["unhashable"]), CloudErrorKind.OTHER),
    ],
    ids=[
        "invalid-token",
        "login-failed",
        "login-401",
        "login-403",
        "login-invalid-token",
        "429",
        "login-429",
        "500",
        "login-503",
        "400",
        "text-429",
        "no-args",
        "login-network",
        "login-no-token",
        "unhashable",
    ],
)
def test_classify_error_returns_kind(
    error: ConnectionException, kind: CloudErrorKind
) -> None:
    """Test each library error gets the right kind."""
    assert classify_error(error) is kind


@pytest.mark.parametrize(
    ("error", "text"),
    [
        (ConnectionException(500), "HTTP 500"),
        (login_error(ConnectionException(401)), "HTTP 401"),
        (ConnectionException("Invalid token"), "Invalid token"),
        (login_error(aiohttp.ClientError("refused")), "refused"),
        (login_error(KeyError()), "KeyError"),
        (ConnectionException(), "no answer"),
        (TimeoutError(), "TimeoutError"),
        (aiohttp.ClientError("reset"), "reset"),
    ],
    ids=[
        "status",
        "login-status",
        "text",
        "login-network",
        "login-empty-cause",
        "no-args",
        "timeout",
        "network",
    ],
)
def test_describe_error_returns_short_text(error: Exception, text: str) -> None:
    """Test the error text shown in messages."""
    assert describe_error(error) == text


ACTIONS: list[tuple[str, str, dict[str, Any]]] = [
    (
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: "climate.nimbus", ATTR_HVAC_MODE: HVACMode.AUTO},
    ),
    (
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: "climate.nimbus", ATTR_PRESET_MODE: "Summer"},
    ),
    (
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: "climate.nimbus", ATTR_TEMPERATURE: 21},
    ),
    (
        WATER_HEATER_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: "water_heater.nimbus", ATTR_TEMPERATURE: 52},
    ),
    (
        WATER_HEATER_DOMAIN,
        SERVICE_SET_OPERATION_MODE,
        {ATTR_ENTITY_ID: "water_heater.nimbus", ATTR_OPERATION_MODE: "Always active"},
    ),
    (
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: "select.nimbus_plant_mode",
            ATTR_OPTION: "Summer",
        },
    ),
    (
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.nimbus_zone_1_heating_flow_temperature",
            ATTR_VALUE: 40,
        },
    ),
    (
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.nimbus_automatic_thermoregulation"},
    ),
]
ACTION_IDS = [
    "climate-hvac-mode",
    "climate-preset",
    "climate-temperature",
    "water-heater-temperature",
    "water-heater-operation-mode",
    "select",
    "number",
    "switch",
]


@pytest.mark.parametrize(("domain", "service", "data"), ACTIONS, ids=ACTION_IDS)
@pytest.mark.parametrize(
    ("error", "key"),
    [
        (ConnectionException(500), "action_failed"),
        (ConnectionException(429, b"body"), "action_rate_limited"),
        (ConnectionException("Login failed (password changed?)"), "action_auth_failed"),
        (aiohttp.ClientError("reset"), "action_failed"),
        (aiohttp.InvalidURL("bad"), "action_failed"),
        (ValueError("Comfort temperature is unknown"), "action_missing_value"),
    ],
    ids=["server", "rate-limit", "auth", "network", "invalid-url", "missing-value"],
)
async def test_entity_action_cloud_error_raises_ha_error(
    hass: HomeAssistant,
    init_full_integration: MockConfigEntry,
    api: MagicMock,
    caplog: pytest.LogCaptureFixture,
    domain: str,
    service: str,
    data: dict[str, Any],
    error: Exception,
    key: str,
) -> None:
    """Test a cloud error of an entity action becomes a translated HA error."""
    api.async_set_property.side_effect = error

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(domain, service, data, blocking=True)

    assert not isinstance(exc_info.value, ServiceValidationError)
    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == key
    assert tracebacks(caplog) == []


async def test_entity_action_error_message_has_status(
    hass: HomeAssistant, init_full_integration: MockConfigEntry, api: MagicMock
) -> None:
    """Test the message of a failed action names the HTTP status."""
    api.async_set_property.side_effect = ConnectionException(500)

    with pytest.raises(HomeAssistantError, match=r"\(HTTP 500\)"):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "switch.nimbus_automatic_thermoregulation"},
            blocking=True,
        )


async def test_entity_action_missing_value_message(
    hass: HomeAssistant, init_full_integration: MockConfigEntry, api: MagicMock
) -> None:
    """Test the message of a change the library refused names the missing value."""
    api.async_set_property.side_effect = ValueError("Comfort temperature is unknown")

    with pytest.raises(HomeAssistantError, match=r"\(Comfort temperature is unknown\)"):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "switch.nimbus_automatic_thermoregulation"},
            blocking=True,
        )


async def test_entity_action_auth_error_starts_reauth(
    hass: HomeAssistant, init_full_integration: MockConfigEntry, api: MagicMock
) -> None:
    """Test a refused login during an action asks for a new password at once."""
    api.async_set_property.side_effect = ConnectionException("Invalid token")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "switch.nimbus_automatic_thermoregulation"},
            blocking=True,
        )
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_entity_action_error_shows_earlier_writes(
    hass: HomeAssistant,
    properties: dict[str, Any],
    mock_ariston: MagicMock,
    config_entry: MockConfigEntry,
    api: MagicMock,
) -> None:
    """Test the writes that worked before a failed one show in the states."""
    set_item(properties, "PlantMode", value=PlantMode.SUMMER.value)
    set_item(properties, "ZoneMode", value=ZoneMode.TIME_PROGRAM.value)
    await setup_integration(hass, config_entry)
    api.async_set_property.side_effect = [None, ConnectionException(500)]

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: "climate.nimbus", ATTR_HVAC_MODE: HVACMode.HEAT},
            blocking=True,
        )

    assert hass.states.get("select.nimbus_plant_mode").state == "Winter"


def entity_classes() -> list[type[AristonEntity]]:
    """Return every entity class of the integration."""
    for platform in PLATFORMS:
        importlib.import_module(f"custom_components.ariston_net.{platform}")
    classes = []
    pending = [AristonEntity]
    while pending:
        cls = pending.pop()
        classes.append(cls)
        pending.extend(cls.__subclasses__())
    return classes


HA_HOOKS = {"async_added_to_hass", "async_will_remove_from_hass", "async_update"}


@pytest.mark.parametrize(
    "cls", entity_classes(), ids=lambda cls: f"{cls.__module__}.{cls.__name__}"
)
def test_entity_actions_use_cloud_action(cls: type[AristonEntity]) -> None:
    """Test every action method of an entity has the cloud_action wrapper."""
    actions = [
        name
        for name, member in vars(cls).items()
        if name.startswith("async_")
        and name not in HA_HOOKS
        and inspect.iscoroutinefunction(member)
    ]

    assert [
        name for name in actions if not hasattr(vars(cls)[name], "__wrapped__")
    ] == []
