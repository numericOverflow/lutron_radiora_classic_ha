"""Message parser for RadioRA Classic RS-232 protocol.

Buffers incoming bytes, splits on CR delimiter, routes to typed message constructors.
"""

from datetime import datetime, timezone

from .const import ButtonState, System, ZoneState
from .messages import (
    AnyMessage,
    CommandError,
    LEDMap,
    LocalZoneChange,
    MasterButtonPress,
    UnknownMessage,
    VersionInfo,
    ZoneMap,
)


class MessageParser:
    """Stateless-ish parser for RadioRA Classic RS-232 messages.

    Buffers incoming bytes, splits on CR delimiter, routes to
    typed message constructors.
    """

    def __init__(self) -> None:
        self._buffer = b""

    def feed(self, data: bytes) -> list[AnyMessage]:
        """Feed raw bytes, return list of complete parsed messages.

        May return empty list if no complete message yet (buffering).
        """
        self._buffer += data
        messages: list[AnyMessage] = []

        while b"\r" in self._buffer:
            line_bytes, self._buffer = self._buffer.split(b"\r", 1)
            line = line_bytes.decode("ascii", errors="replace").strip()
            if not line:
                continue
            msg = self.parse_line(line)
            if msg is not None:
                messages.append(msg)

        return messages

    def reset(self) -> None:
        """Clear internal buffer (call on reconnection)."""
        self._buffer = b""

    @staticmethod
    def parse_line(line: str) -> AnyMessage | None:
        """Parse a single CR-terminated line into a typed message.

        Returns None for empty lines.
        """
        line = line.strip()
        if not line:
            return None

        now = datetime.now(timezone.utc)

        # Error response
        if line == "!":
            return CommandError(raw=line, timestamp=now)

        parts = line.split(",")
        verb = parts[0]

        if verb == "LZC":
            return _parse_lzc(parts, line, now)
        elif verb == "ZMP":
            return _parse_zmp(parts, line, now)
        elif verb == "LMP":
            return _parse_lmp(parts, line, now)
        elif verb == "MBP":
            return _parse_mbp(parts, line, now)
        elif verb == "REV":
            return _parse_rev(parts, line, now)
        else:
            return UnknownMessage(raw=line, timestamp=now)


def _parse_system(parts: list[str], index: int) -> System:
    """Parse optional system field (e.g. 'S1', 'S2') at given index."""
    if index < len(parts):
        sys_str = parts[index]
        if sys_str == "S1":
            return System.S1
        elif sys_str == "S2":
            return System.S2
    return System.NONE


def _parse_lzc(parts: list[str], raw: str, ts: datetime) -> LocalZoneChange | UnknownMessage:
    """Parse LZC,<zone>,<state>(,<system>)."""
    try:
        zone = int(parts[1])
        state = ZoneState(parts[2])
        system = _parse_system(parts, 3)
        return LocalZoneChange(raw=raw, timestamp=ts, zone=zone, state=state, system=system)
    except (IndexError, ValueError):
        return UnknownMessage(raw=raw, timestamp=ts)


def _parse_zmp(parts: list[str], raw: str, ts: datetime) -> ZoneMap | UnknownMessage:
    """Parse ZMP,<32-char bitmap>(,<system>)."""
    try:
        states = parts[1]
        system = _parse_system(parts, 2)
        return ZoneMap(raw=raw, timestamp=ts, states=states, system=system)
    except (IndexError, ValueError):
        return UnknownMessage(raw=raw, timestamp=ts)


def _parse_lmp(parts: list[str], raw: str, ts: datetime) -> LEDMap | UnknownMessage:
    """Parse LMP,<15-char bitmap>."""
    try:
        bitmap = parts[1]
        return LEDMap(raw=raw, timestamp=ts, bitmap=bitmap)
    except (IndexError, ValueError):
        return UnknownMessage(raw=raw, timestamp=ts)


def _parse_mbp(parts: list[str], raw: str, ts: datetime) -> MasterButtonPress | UnknownMessage:
    """Parse MBP,<master_control>,<button>,<state>(,<system>)."""
    try:
        master_control = int(parts[1])
        button = int(parts[2])
        state = ButtonState(parts[3])
        system = _parse_system(parts, 4)
        return MasterButtonPress(
            raw=raw,
            timestamp=ts,
            master_control=master_control,
            button=button,
            state=state,
            system=system,
        )
    except (IndexError, ValueError):
        return UnknownMessage(raw=raw, timestamp=ts)


def _parse_rev(parts: list[str], raw: str, ts: datetime) -> VersionInfo | UnknownMessage:
    """Parse REV,<master_version>,<slave_version>."""
    try:
        master_version = parts[1]
        slave_version = parts[2]
        return VersionInfo(
            raw=raw, timestamp=ts, master_version=master_version, slave_version=slave_version
        )
    except (IndexError, ValueError):
        return UnknownMessage(raw=raw, timestamp=ts)
