"""Tests for the handling of Ariston cloud errors."""

from __future__ import annotations

import aiohttp
from ariston.ariston_api import ConnectionException
import pytest

from custom_components.ariston_net.errors import (
    CloudErrorKind,
    classify_error,
    describe_error,
)


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
