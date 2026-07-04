"""Typed response dataclasses for RadioRA Classic RS-232 feedback messages."""

from dataclasses import dataclass
from datetime import datetime

from .const import ButtonState, System, ZoneState


@dataclass(frozen=True)
class RadioRAMessage:
    """Base for all messages received from RA-RS232."""

    raw: str
    timestamp: datetime


@dataclass(frozen=True)
class LocalZoneChange(RadioRAMessage):
    """LZC feedback — a zone was changed locally (wall switch/dimmer).

    Format: LZC,<zone>,<state>(,<system>)
    Examples: 'LZC,03,CHG', 'LZC,04,ON,S2'
    """

    zone: int  # 1-32
    state: ZoneState  # ON, OFF, or CHG
    system: System  # S1, S2, or NONE


@dataclass(frozen=True)
class ZoneMap(RadioRAMessage):
    """ZMP feedback — full state of all 32 zones.

    Format: ZMP,<32-char bitmap>(,<system>)
    Example: 'ZMP,11001011001011001011001011001000,S1'
    Chars: '1'=ON, '0'=OFF, 'X'=unassigned
    """

    states: str  # 32-char string of '0', '1', 'X'
    system: System

    def is_zone_on(self, zone: int) -> bool | None:
        """Check if zone is on. Returns None if unassigned ('X')."""
        if zone < 1 or zone > len(self.states):
            return None
        ch = self.states[zone - 1]
        if ch == "X":
            return None
        return ch == "1"


@dataclass(frozen=True)
class LEDMap(RadioRAMessage):
    """LMP feedback — state of all 15 phantom button LEDs.

    Format: LMP,<15-char bitmap>
    Example: 'LMP,100010000000000'
    Chars: '1'=ON (scene active), '0'=OFF
    """

    bitmap: str  # 15-char string of '0', '1'

    def is_button_active(self, button: int) -> bool:
        """Check if phantom button LED is lit (scene active)."""
        if button < 1 or button > len(self.bitmap):
            return False
        return self.bitmap[button - 1] == "1"


@dataclass(frozen=True)
class MasterButtonPress(RadioRAMessage):
    """MBP feedback — a master control button was pressed.

    Format: MBP,<master_control>,<button>,<state>(,<system>)
    """

    master_control: int
    button: int
    state: ButtonState
    system: System


@dataclass(frozen=True)
class VersionInfo(RadioRAMessage):
    """REV feedback — firmware version response.

    Format: REV,<master_version>,<slave_version>
    """

    master_version: str
    slave_version: str


@dataclass(frozen=True)
class CommandError(RadioRAMessage):
    """'!' response — controller did not recognize the command.

    This is ONLY sent for invalid/unknown commands. Valid commands
    either return data (ZMPI->ZMP, LMP->LMP, VERI->REV) or return
    nothing (SDL, SSL, BP, LZCMON, etc. are fire-and-forget).
    """


@dataclass(frozen=True)
class UnknownMessage(RadioRAMessage):
    """Unrecognized message from controller."""


# Union type for callbacks
AnyMessage = (
    LocalZoneChange
    | ZoneMap
    | LEDMap
    | MasterButtonPress
    | VersionInfo
    | CommandError
    | UnknownMessage
)
