"""Sort the errors of the Ariston cloud library and turn them into HA errors."""

from __future__ import annotations

from enum import StrEnum

import aiohttp
from ariston_net_api.ariston_api import ConnectionException
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

HTTP_TOO_MANY_REQUESTS = 429
# Only a login wraps network errors, other requests raise them as they are.
CLOUD_ERRORS = (ConnectionException, aiohttp.ClientError, TimeoutError)
# The library raises these after a failed new login with the saved password.
AUTH_ERROR_TEXTS = frozenset({"Invalid token", "Login failed (password changed?)"})


class CloudErrorKind(StrEnum):
    """Kind of a cloud error, for the reaction to it."""

    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    SERVER = "server"
    OTHER = "other"


def _reason(error: ConnectionException) -> object:
    """Return the first argument of the error, or of the error a login wraps.

    A login wraps every error in an empty ConnectionException.
    """
    if error.args:
        return error.args[0]
    cause = error.__cause__
    if isinstance(cause, ConnectionException) and cause.args:
        return cause.args[0]
    return None


def error_status(error: ConnectionException) -> int | None:
    """Return the HTTP status of the error, None for other errors."""
    reason = _reason(error)
    return reason if isinstance(reason, int) else None


def classify_error(error: ConnectionException) -> CloudErrorKind:
    """Return the kind of a library error."""
    reason = _reason(error)
    if isinstance(reason, str) and reason in AUTH_ERROR_TEXTS:
        return CloudErrorKind.AUTH
    status = error_status(error)
    if status is None:
        return CloudErrorKind.OTHER
    if status == HTTP_TOO_MANY_REQUESTS:
        return CloudErrorKind.RATE_LIMIT
    if status >= 500:
        return CloudErrorKind.SERVER
    # Nobody knows the status of a wrong password, so take any refused login.
    if not error.args and 400 <= status < 500:
        return CloudErrorKind.AUTH
    return CloudErrorKind.OTHER


def describe_error(error: Exception) -> str:
    """Return a short text of the error for messages."""
    if not isinstance(error, ConnectionException):
        return str(error) or type(error).__name__
    if (status := error_status(error)) is not None:
        return f"HTTP {status}"
    if (reason := _reason(error)) is not None:
        return str(reason)
    cause = error.__cause__
    if cause is None:
        return "no answer"
    return str(cause) or type(cause).__name__


def action_error(
    hass: HomeAssistant, entry: ConfigEntry, error: Exception
) -> HomeAssistantError:
    """Return the error to show for a failed change. An auth error starts reauth."""
    kind = (
        classify_error(error)
        if isinstance(error, ConnectionException)
        else CloudErrorKind.OTHER
    )
    match kind:
        case CloudErrorKind.AUTH:
            entry.async_start_reauth(hass)
            key = "action_auth_failed"
        case CloudErrorKind.RATE_LIMIT:
            key = "action_rate_limited"
        case _:
            key = "action_failed"
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders={"error": describe_error(error)},
    )
