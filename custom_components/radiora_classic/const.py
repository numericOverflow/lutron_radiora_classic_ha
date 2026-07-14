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
# When True, forces DEBUG level on the integration's logger tree so that
# every TX/RX serial line is written to home-assistant.log. Equivalent to
# raising the level for `custom_components.radiora_classic` in
# Settings → System → Logs (see manifest.json "loggers").
CONF_DEBUG_LOGGING: Final = "debug_logging"

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
DEFAULT_DEBUG_LOGGING: Final = False

# CSV limits
MAX_CSV_SIZE: Final = 500_000  # 500KB
MAX_CSV_ROWS: Final = 256
