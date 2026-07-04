"""pyradiora-classic — Python client for Lutron RadioRA Classic RS-232."""

from .client import RadioRAClient
from .client_sync import RadioRAClientSync
from .const import (
    BAUD_RATE,
    BUTTON_ALL_OFF,
    BUTTON_ALL_ON,
    MAX_DIMMER_LEVEL,
    MAX_ZONES,
    ButtonState,
    MonitorType,
    SwitchState,
    System,
    ZoneState,
)
from .exceptions import (
    RadioRACommandError,
    RadioRAConnectionError,
    RadioRAConnectionLost,
    RadioRAError,
    RadioRAProtocolError,
    RadioRATimeoutError,
)
from .messages import (
    AnyMessage,
    LEDMap,
    LocalZoneChange,
    MasterButtonPress,
    PromptReady,
    RadioRAMessage,
    UnknownMessage,
    VersionInfo,
    ZoneMap,
)

__all__ = [
    # Clients
    "RadioRAClient",
    "RadioRAClientSync",
    # Enums
    "System",
    "ZoneState",
    "ButtonState",
    "SwitchState",
    "MonitorType",
    # Messages
    "AnyMessage",
    "RadioRAMessage",
    "LocalZoneChange",
    "ZoneMap",
    "LEDMap",
    "MasterButtonPress",
    "VersionInfo",
    "PromptReady",
    "UnknownMessage",
    # Exceptions
    "RadioRAError",
    "RadioRAConnectionError",
    "RadioRAConnectionLost",
    "RadioRATimeoutError",
    "RadioRAProtocolError",
    "RadioRACommandError",
    # Constants
    "BAUD_RATE",
    "MAX_ZONES",
    "MAX_DIMMER_LEVEL",
    "BUTTON_ALL_ON",
    "BUTTON_ALL_OFF",
]
