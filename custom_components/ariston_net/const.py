"""Constants for the Ariston integration."""

from typing import Final

DOMAIN: Final[str] = "ariston_net"
NAME: Final[str] = "Ariston NET"
COORDINATOR: Final[str] = "coordinator"
ENERGY_COORDINATOR: Final[str] = "energy_coordinator"
ENERGY_SCAN_INTERVAL: Final[str] = "energy_scan_interval"
BUS_ERRORS_COORDINATOR: Final[str] = "bus_errors_coordinator"
BUS_ERRORS_SCAN_INTERVAL: Final[str] = "bus_errors_scan_interval"
ENABLE_ENERGY: Final[str] = "enable_energy"
ENABLE_BUS_ERRORS: Final[str] = "enable_bus_errors"
API_URL_SETTING: Final[str] = "api_url_setting"
API_USER_AGENT: Final[str] = "api_user_agent"

DEFAULT_SCAN_INTERVAL_SECONDS: Final[int] = 180
DEFAULT_ENERGY_SCAN_INTERVAL_MINUTES: Final[int] = 60
DEFAULT_BUS_ERRORS_SCAN_INTERVAL_SECONDS: Final[int] = 600
MIN_SCAN_INTERVAL_SECONDS: Final[int] = 60
MIN_ENERGY_SCAN_INTERVAL_MINUTES: Final[int] = 15
MIN_BUS_ERRORS_SCAN_INTERVAL_SECONDS: Final[int] = 60
MAX_SCAN_INTERVAL_SECONDS: Final[int] = 86400
MAX_ENERGY_SCAN_INTERVAL_MINUTES: Final[int] = 1440
MAX_BUS_ERRORS_SCAN_INTERVAL_SECONDS: Final[int] = 86400

ATTR_TARGET_TEMP_STEP: Final[str] = "target_temp_step"
ATTR_HEAT_REQUEST: Final[str] = "heat_request"
ATTR_ECONOMY_TEMP: Final[str] = "economy_temp"
ATTR_HOLIDAY: Final[str] = "holiday"
ATTR_ZONE: Final[str] = "zone_number"
ATTR_ERRORS: Final[str] = "errors"

EXTRA_STATE_ATTRIBUTE: Final[str] = "Attribute"
EXTRA_STATE_DEVICE_METHOD: Final[str] = "DeviceMethod"
