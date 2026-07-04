"""Blocking client for RadioRA Classic RS-232 control.

Thin sync wrapper for scripts and CLI tools. No monitoring loop,
no reconnection, no callbacks. Request/response only.
"""

from __future__ import annotations

from . import commands
from .const import (
    ButtonState,
    MonitorType,
    SwitchState,
    System,
)
from .exceptions import RadioRAConnectionLost, RadioRATimeoutError
from .messages import (
    AnyMessage,
    LEDMap,
    VersionInfo,
    ZoneMap,
)
from .protocol import MessageParser
from .transport_sync import SyncTransport


class RadioRAClientSync:
    """Blocking client for RadioRA Classic RS-232 control.

    For scripts, CLI tools, and testing. No background tasks.
    """

    def __init__(self, url: str, timeout: float = 2.0, bridged: bool = False) -> None:
        self._url = url
        self._timeout = timeout
        self._bridged = bridged
        self._transport = SyncTransport(url, timeout)
        self._parser = MessageParser()

    # --- Connection ---

    def connect(self) -> None:
        """Connect to RA-RS232."""
        self._transport.connect()

    def disconnect(self) -> None:
        """Disconnect."""
        self._transport.close()

    @property
    def connected(self) -> bool:
        """Whether connected."""
        return self._transport.connected

    # --- Zone Control ---

    def set_dimmer_level(
        self,
        zone: int,
        level: int,
        fade_sec: int | None = None,
        system: System = System.NONE,
    ) -> None:
        """Set dimmer to level (0-100)."""
        cmd = commands.set_dimmer_level(zone, level, fade_sec, system)
        self._send(cmd)

    def switch_on(
        self,
        zone: int,
        delay_sec: int | None = None,
        system: System = System.NONE,
    ) -> None:
        """Turn switch zone ON."""
        cmd = commands.set_switch_level(zone, SwitchState.ON, delay_sec, system)
        self._send(cmd)

    def switch_off(
        self,
        zone: int,
        delay_sec: int | None = None,
        system: System = System.NONE,
    ) -> None:
        """Turn switch zone OFF."""
        cmd = commands.set_switch_level(zone, SwitchState.OFF, delay_sec, system)
        self._send(cmd)

    # --- Phantom Buttons ---

    def button_press(
        self,
        button: int,
        state: ButtonState = ButtonState.ON,
        fade_sec: int | None = None,
        system: System = System.NONE,
    ) -> None:
        """Press a phantom button."""
        cmd = commands.button_press(button, state, fade_sec, system)
        self._send(cmd)

    def raise_button(self, button: int, system: System = System.NONE) -> None:
        """Start raise-ramp on phantom button."""
        cmd = commands.raise_button(button, system)
        self._send(cmd)

    def lower_button(self, button: int, system: System = System.NONE) -> None:
        """Start lower-ramp on phantom button."""
        cmd = commands.lower_button(button, system)
        self._send(cmd)

    def stop_raise_lower(self) -> None:
        """Stop any active raise/lower ramp."""
        self._send(commands.stop_raise_lower())

    # --- State Queries ---

    def get_zone_map(self) -> list[ZoneMap]:
        """Send ZMPI, block until response(s) received, return them.

        Returns:
            List of 1 ZoneMap (single) or 2 ZoneMaps (bridged: S1 + S2).
        """
        expected_count = 2 if self._bridged else 1
        self._send(commands.zone_map_inquiry())

        results: list[ZoneMap] = []
        for _ in range(expected_count):
            msg = self._read_typed(ZoneMap)
            if msg is not None:
                results.append(msg)
            else:
                break

        if not results:
            raise RadioRATimeoutError("No ZMP response received for ZMPI")
        return results

    def get_led_map(self) -> LEDMap:
        """Query current state of all 15 phantom button LEDs."""
        self._send(commands.phantom_led_status())
        msg = self._read_typed(LEDMap)
        if msg is None:
            raise RadioRATimeoutError("No LMP response received")
        return msg

    def get_version(self) -> VersionInfo:
        """Query firmware version (VERI command)."""
        self._send(commands.version_inquiry())
        msg = self._read_typed(VersionInfo)
        if msg is None:
            raise RadioRATimeoutError("No REV response received")
        return msg

    # --- Monitoring ---

    def enable_monitoring(self) -> None:
        """Enable all monitoring. Use read_message() to get events."""
        self._send(commands.enable_monitoring(MonitorType.ZONE_CHANGE))
        self._send(commands.enable_monitoring(MonitorType.BUTTON_PRESS))
        self._send(commands.enable_monitoring(MonitorType.ZONE_MAP))

    def disable_monitoring(self) -> None:
        """Disable all monitoring."""
        self._send(commands.disable_monitoring(MonitorType.ZONE_CHANGE))
        self._send(commands.disable_monitoring(MonitorType.BUTTON_PRESS))
        self._send(commands.disable_monitoring(MonitorType.ZONE_MAP))

    def read_message(self, timeout: float | None = None) -> AnyMessage | None:
        """Block and read next message from controller.

        Returns None on timeout.
        """
        line = self._transport.read_line(timeout=timeout)
        if line is None:
            return None
        msgs = self._parser.feed((line + "\r").encode("ascii"))
        return msgs[0] if msgs else None

    # --- Raw ---

    def send_raw(self, command: str) -> str | None:
        """Send raw command string, return raw response (or None on timeout)."""
        self._send(command)
        return self._transport.read_line()

    # --- Internals ---

    def _send(self, cmd: str) -> None:
        """Send command via transport."""
        if not self._transport.connected:
            raise RadioRAConnectionLost("Not connected")
        self._transport.write(cmd)

    def _read_typed(self, msg_type: type) -> AnyMessage | None:
        """Read lines until we get the expected message type or timeout."""
        # Try up to 5 reads to find the right message type
        for _ in range(5):
            line = self._transport.read_line()
            if line is None:
                return None
            msgs = self._parser.feed((line + "\r").encode("ascii"))
            for msg in msgs:
                if isinstance(msg, msg_type):
                    return msg
        return None
