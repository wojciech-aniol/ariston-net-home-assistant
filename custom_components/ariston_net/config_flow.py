"""Config flow for Ariston integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from ariston import Ariston, DeviceAttribute
from ariston.ariston_api import ConnectionException
from ariston.const import ARISTON_API_URL, ARISTON_USER_AGENT
from homeassistant import config_entries
from homeassistant.const import (
    CONF_DEVICE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
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
    MIN_BUS_ERRORS_SCAN_INTERVAL_SECONDS,
    MIN_ENERGY_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_SECONDS,
)
from .coordinator import interval_option
from .errors import CLOUD_ERRORS, CloudErrorKind, classify_error, describe_error

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required("advanced"): section(
            vol.Schema(
                {
                    vol.Optional(API_URL_SETTING, default=ARISTON_API_URL): str,
                    vol.Optional(API_USER_AGENT, default=ARISTON_USER_AGENT): str,
                }
            ),
            {"collapsed": True},
        ),
    }
)


def _interval(minimum: int, unit: str) -> vol.All:
    """Return the field of an interval option, a whole number from a minimum."""
    return vol.All(
        NumberSelector(
            NumberSelectorConfig(
                min=minimum,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement=unit,
            )
        ),
        vol.Coerce(int),
    )


class AristonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Ariston Config Flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize Ariston config flow."""
        self.cloud_username: str = ""
        self.cloud_password: str = ""
        self.cloud_api_url: str = ARISTON_API_URL
        self.cloud_api_user_agent: str = ARISTON_USER_AGENT
        self.cloud_devices = {}

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
            self.cloud_api_url = user_input["advanced"][API_URL_SETTING]
            self.cloud_api_user_agent = user_input["advanced"][API_USER_AGENT]
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
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_create_or_update_entry(self, cloud_device):
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
            # Also reloads an entry whose setup failed on the old login.
            return self.async_update_reload_and_abort(
                entry, data=data, reason="already_configured"
            )

        return self.async_create_entry(
            title=cloud_device[DeviceAttribute.NAME], data=data
        )

    async def async_step_select(self, user_input=None):
        """Multiple device found, select one of them."""
        errors = {}
        if user_input is not None:
            return await self.async_create_or_update_entry(
                self.cloud_devices[user_input["select_device"]]
            )

        select_schema = vol.Schema(
            {vol.Required("select_device"): vol.In(list(self.cloud_devices))}
        )

        return self.async_show_form(
            step_id="select", data_schema=select_schema, errors=errors
        )

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
            else:
                gateway = entry.data[CONF_DEVICE][DeviceAttribute.GW]
                if all(
                    device[DeviceAttribute.GW] != gateway for device in cloud_devices
                ):
                    return self.async_abort(reason="unique_id_mismatch")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={"username": entry.data[CONF_USERNAME]},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return AristonOptionsFlow()


class AristonOptionsFlow(config_entries.OptionsFlowWithReload):
    """Handle Ariston options."""

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        scan_interval = interval_option(options, CONF_SCAN_INTERVAL)
        energy_scan_interval = interval_option(options, ENERGY_SCAN_INTERVAL)
        bus_errors_scan_interval = interval_option(options, BUS_ERRORS_SCAN_INTERVAL)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=scan_interval,
                    ): _interval(MIN_SCAN_INTERVAL_SECONDS, "s"),
                    vol.Optional(
                        ENABLE_ENERGY,
                        default=options.get(ENABLE_ENERGY, True),
                    ): bool,
                    vol.Optional(
                        ENERGY_SCAN_INTERVAL,
                        default=energy_scan_interval,
                    ): _interval(MIN_ENERGY_SCAN_INTERVAL_MINUTES, "min"),
                    vol.Optional(
                        ENABLE_BUS_ERRORS,
                        default=options.get(ENABLE_BUS_ERRORS, True),
                    ): bool,
                    vol.Optional(
                        BUS_ERRORS_SCAN_INTERVAL,
                        default=bus_errors_scan_interval,
                    ): _interval(MIN_BUS_ERRORS_SCAN_INTERVAL_SECONDS, "s"),
                }
            ),
            last_step=True,
        )
