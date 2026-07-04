"""Constants for the Lutron RadioRA Classic integration."""

from typing import Final

DOMAIN: Final = "radiora_classic"

# Config keys (entry.data)
CONF_URL: Final = "url"
CONF_BRIDGED: Final = "bridged"

# Config keys (entry.options)
CONF_CONTROLLER_ID: Final = "controller_id"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_ZONES: Final = "zones"
CONF_PHANTOM_BUTTONS: Final = "phantom_buttons"
CONF_MASTER_CONTROLS: Final = "master_controls"

# Zone config keys
CONF_ZONE_NUMBER: Final = "zone"
CONF_MODE: Final = "mode"
CONF_FADE_SEC: Final = "fade_sec"
CONF_SYSTEM: Final = "system"
CONF_BUTTON_NUMBER: Final = "button"
CONF_MASTER_CONTROL: Final = "master_control"

# Defaults
DEFAULT_POLL_INTERVAL: Final = 30
DEFAULT_ZONE_MODE: Final = "dimmer"

# CSV limits
MAX_CSV_SIZE: Final = 500_000  # 500KB
MAX_CSV_ROWS: Final = 256
