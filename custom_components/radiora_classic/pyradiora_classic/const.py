"""Protocol constants and enums for Lutron RadioRA Classic RS-232."""

from enum import Enum, IntEnum

# --- Protocol Settings ---
BAUD_RATE = 9600
CR = b"\r"
ENCODING = "ascii"
MAX_ZONES = 32
MAX_PHANTOM_BUTTONS = 15
MAX_DIMMER_LEVEL = 100
MAX_FADE_SECONDS = 240
MAX_DELAY_SECONDS = 240
BUTTON_ALL_ON = 16
BUTTON_ALL_OFF = 17


class System(IntEnum):
    """RadioRA system identifier (for bridged Chronos configurations)."""

    NONE = 0  # Single system (no bridge) — omit from command
    S1 = 1  # System 1
    S2 = 2  # System 2


class ZoneState(Enum):
    """Zone state as reported by LZC feedback."""

    ON = "ON"
    OFF = "OFF"
    CHG = "CHG"  # Changed (dimmer level changed, but still on)


class ButtonState(Enum):
    """Phantom button command state."""

    ON = "ON"
    OFF = "OFF"
    TOG = "TOG"


class SwitchState(Enum):
    """Switch command state (ON or OFF only).

    The SSL command only accepts ON or OFF. TOG is NOT valid for switches —
    use button_press() with ButtonState.TOG for phantom buttons instead.
    """

    ON = "ON"
    OFF = "OFF"


class MonitorType(Enum):
    """Types of monitoring that can be enabled/disabled."""

    ZONE_CHANGE = "LZCM"  # Local Zone Change monitoring
    BUTTON_PRESS = "MBPM"  # Master Button Press monitoring
    ZONE_MAP = "ZMPM"  # Zone Map change monitoring
