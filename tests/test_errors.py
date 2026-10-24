"""Tests for the handling of Ariston cloud errors."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import aiohttp
from ariston.ariston_api import ConnectionException
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
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ariston_net.const import DOMAIN
from custom_components.ariston_net.errors import (
    CloudErrorKind,
    classify_error,
    describe_error,
)

from .conftest import tracebacks


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
            ATTR_ENTITY_ID: "select.nimbus_ariston_net_plant_mode",
            ATTR_OPTION: "Summer",
        },
    ),
    (
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.nimbus_ariston_net_heating_flow_temperature_1",
            ATTR_VALUE: 40,
        },
    ),
    (
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.nimbus_ariston_net_automatic_thermoregulation"},
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
    ],
    ids=["server", "rate-limit", "auth", "network"],
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
            {ATTR_ENTITY_ID: "switch.nimbus_ariston_net_automatic_thermoregulation"},
            blocking=True,
        )
