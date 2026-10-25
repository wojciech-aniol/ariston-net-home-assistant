"""Config flow for Ariston integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from ariston_net_api import Ariston, DeviceAttribute
from ariston_net_api.ariston_api import ConnectionException
from ariston_net_api.const import ARISTON_API_URL, ARISTON_USER_AGENT
from homeassistant import config_entries
from homeassistant.const import (
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    UnitOfTime,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
import voluptuous as vol

from .const import (
    API_URL_SETTING,
    API_USER_AGENT,
    BUS_ERRORS_SCAN_INTERVAL,
    DOMAIN,
    ENABLE_BUS_ERRORS,
    ENABLE_ENERGY,
    ENERGY_SCAN_INTERVAL,
)
from .coordinator import INTERVAL_OPTIONS, interval_option
from .errors import CLOUD_ERRORS, CloudErrorKind, classify_error, describe_error

_LOGGER = logging.getLogger(__name__)

API_DEFAULTS: dict[str, str] = {
    API_URL_SETTING: ARISTON_API_URL,
    API_USER_AGENT: ARISTON_USER_AGENT,
}

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        # Optional, so a login alone is enough. No default here: the form
        # would then show it instead of the field defaults.
        vol.Optional("advanced"): section(
            vol.Schema(
                {
                    vol.Optional(key, default=default): str
                    for key, default in API_DEFAULTS.items()
                }
            ),
            {"collapsed": True},
        ),
    }
)

STEP_RECONFIGURE_DATA_SCHEMA = vol.Schema(
    {vol.Required(key): str for key in API_DEFAULTS}
)


# Limits of each interval, like {"scan_interval_min": "60"}, for the texts.
INTERVAL_LIMITS: dict[str, str] = {
    f"{key}_{name}": str(limit)
    for key, (_, minimum, maximum) in INTERVAL_OPTIONS.items()
    for name, limit in (("min", minimum), ("max", maximum))
}


class _IntervalSelector(NumberSelector):
    """Number box that sends its limits to the form but does not check them.

    The options step checks them, so the error can be translated.
    """

    def __call__(self, data: Any) -> float:
        """Accept any number."""
        return vol.Coerce(float)(data)


def _interval(key: str, unit: UnitOfTime) -> _IntervalSelector:
    """Return the field of an interval option."""
    _, minimum, maximum = INTERVAL_OPTIONS[key]
    return _IntervalSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


def _interval_errors(user_input: Mapping[str, Any]) -> dict[str, str]:
    """Return an error for each interval that is not a whole number within limits."""
    return {
        key: f"invalid_{key}"
        for key, (_, minimum, maximum) in INTERVAL_OPTIONS.items()
        if not (user_input[key].is_integer() and minimum <= user_input[key] <= maximum)
    }


def _clean_api_settings(settings: Mapping[str, str]) -> dict[str, str]:
    """Strip the API settings and end the URL with "/".

    The library adds paths to the URL with no "/" between them.
    """
    url = settings[API_URL_SETTING].strip()
    return {
        API_URL_SETTING: url if url.endswith("/") else f"{url}/",
        API_USER_AGENT: settings[API_USER_AGENT].strip(),
    }


def _has_entry_device(
    entry: config_entries.ConfigEntry, cloud_devices: list[dict[str, Any]]
) -> bool:
    """Return whether the account still has the device of the entry."""
    gateway = entry.data[CONF_DEVICE][DeviceAttribute.GW]
    return any(device[DeviceAttribute.GW] == gateway for device in cloud_devices)


class AristonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Ariston Config Flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize Ariston config flow."""
        self.cloud_username: str = ""
        self.cloud_password: str = ""
        self.cloud_api_url: str = ARISTON_API_URL
        self.cloud_api_user_agent: str = ARISTON_USER_AGENT
        self.cloud_devices: dict[str, dict[str, Any]] = {}

    async def _async_get_devices(
        self, username: str, password: str, api_url: str, user_agent: str
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Log in and return the devices of the account, or an error key."""
        ariston = Ariston()
        try:
            if not await ariston.async_connect(username, password, api_url, user_agent):
                return [], "invalid_auth"
            return await ariston.async_discover(), None
        except CLOUD_ERRORS as error:
            if (
                isinstance(error, ConnectionException)
                and classify_error(error) is CloudErrorKind.AUTH
            ):
                return [], "invalid_auth"
            _LOGGER.debug("Ariston cloud error: %s", describe_error(error))
            return [], "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error while logging in to Ariston")
            return [], "unknown"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self.cloud_username = user_input[CONF_USERNAME]
            self.cloud_password = user_input[CONF_PASSWORD]
            api_settings = _clean_api_settings(
                API_DEFAULTS | user_input.get("advanced", {})
            )
            self.cloud_api_url = api_settings[API_URL_SETTING]
            self.cloud_api_user_agent = api_settings[API_USER_AGENT]
            cloud_devices, error = await self._async_get_devices(
                self.cloud_username,
                self.cloud_password,
                self.cloud_api_url,
                self.cloud_api_user_agent,
            )
            if error:
                errors["base"] = error
            elif not cloud_devices:
                return self.async_abort(reason="no_devices_found")
            elif len(cloud_devices) == 1:
                return await self.async_create_or_update_entry(cloud_devices[0])
            else:
                for device in cloud_devices:
                    name = device[DeviceAttribute.NAME]
                    model = device[DeviceAttribute.SN]
                    list_name = f"{name} - {model}"
                    self.cloud_devices[list_name] = device

                return await self.async_step_select()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_create_or_update_entry(
        self, cloud_device: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Create the entry, or save the new login in the entry of the device."""
        data = {
            CONF_USERNAME: self.cloud_username,
            CONF_PASSWORD: self.cloud_password,
            API_URL_SETTING: self.cloud_api_url,
            API_USER_AGENT: self.cloud_api_user_agent,
            CONF_DEVICE: cloud_device,
        }
        if entry := await self.async_set_unique_id(
            cloud_device[DeviceAttribute.GW], raise_on_progress=False
        ):
            # The API settings are folded away, so a default keeps the saved value.
            for key, default in API_DEFAULTS.items():
                if data[key] == default:
                    data[key] = entry.data.get(key, default)
            # Also reloads an entry whose setup failed on the old login.
            return self.async_update_reload_and_abort(
                entry, data=data, reason="already_configured"
            )

        return self.async_create_entry(
            title=cloud_device[DeviceAttribute.NAME], data=data
        )

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Multiple device found, select one of them."""
        if user_input is not None:
            return await self.async_create_or_update_entry(
                self.cloud_devices[user_input["select_device"]]
            )

        select_schema = vol.Schema(
            {vol.Required("select_device"): vol.In(list(self.cloud_devices))}
        )

        return self.async_show_form(step_id="select", data_schema=select_schema)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Ask for a new password after the cloud refused the saved one."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Check the new password and save it."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            cloud_devices, error = await self._async_get_devices(
                entry.data[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                entry.data.get(API_URL_SETTING, ARISTON_API_URL),
                entry.data.get(API_USER_AGENT, ARISTON_USER_AGENT),
            )
            if error:
                errors["base"] = error
            elif not _has_entry_device(entry, cloud_devices):
                return self.async_abort(reason="unique_id_mismatch")
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={"username": entry.data[CONF_USERNAME]},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Change the API settings and check them with the saved login."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = _clean_api_settings(user_input)
            cloud_devices, error = await self._async_get_devices(
                entry.data[CONF_USERNAME],
                entry.data[CONF_PASSWORD],
                user_input[API_URL_SETTING],
                user_input[API_USER_AGENT],
            )
            # The login is the saved one, so these errors point at the settings.
            if error:
                errors["base"] = (
                    "invalid_api_settings" if error == "invalid_auth" else error
                )
            elif not cloud_devices:
                errors["base"] = "invalid_api_settings"
            elif not _has_entry_device(entry, cloud_devices):
                return self.async_abort(reason="unique_id_mismatch")
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_RECONFIGURE_DATA_SCHEMA,
                user_input
                or {
                    key: entry.data.get(key, default)
                    for key, default in API_DEFAULTS.items()
                },
            ),
            errors=errors,
            description_placeholders=API_DEFAULTS,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> AristonOptionsFlow:
        """Get the options flow for this handler."""
        return AristonOptionsFlow()


class AristonOptionsFlow(config_entries.OptionsFlowWithReload):
    """Handle Ariston options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None and not (errors := _interval_errors(user_input)):
            return self.async_create_entry(
                title="",
                data=user_input
                | {key: int(user_input[key]) for key in INTERVAL_OPTIONS},
            )

        options = self.config_entry.options
        scan_interval = interval_option(options, CONF_SCAN_INTERVAL)
        energy_scan_interval = interval_option(options, ENERGY_SCAN_INTERVAL)
        bus_errors_scan_interval = interval_option(options, BUS_ERRORS_SCAN_INTERVAL)

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=scan_interval,
                ): _interval(CONF_SCAN_INTERVAL, UnitOfTime.SECONDS),
                vol.Optional(
                    ENABLE_ENERGY,
                    default=options.get(ENABLE_ENERGY, True),
                ): bool,
                vol.Optional(
                    ENERGY_SCAN_INTERVAL,
                    default=energy_scan_interval,
                ): _interval(ENERGY_SCAN_INTERVAL, UnitOfTime.MINUTES),
                vol.Optional(
                    ENABLE_BUS_ERRORS,
                    default=options.get(ENABLE_BUS_ERRORS, True),
                ): bool,
                vol.Optional(
                    BUS_ERRORS_SCAN_INTERVAL,
                    default=bus_errors_scan_interval,
                ): _interval(BUS_ERRORS_SCAN_INTERVAL, UnitOfTime.SECONDS),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(data_schema, user_input),
            errors=errors,
            description_placeholders=INTERVAL_LIMITS,
            last_step=True,
        )
