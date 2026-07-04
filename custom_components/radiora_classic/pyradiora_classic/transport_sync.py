"""Blocking transport for RadioRA Classic RS-232.

Uses pyserial's serial_for_url() which handles ALL URL schemes
natively in blocking mode (local serial, RFC 2217, socket://).
"""

from __future__ import annotations

import serial

from .const import BAUD_RATE, ENCODING
from .exceptions import RadioRAConnectionError, RadioRAConnectionLost


class SyncTransport:
    """Blocking transport. Uses pyserial's serial_for_url() for all schemes."""

    def __init__(self, url: str, timeout: float = 2.0) -> None:
        self._url = url
        self._timeout = timeout
        self._serial: serial.Serial | None = None

    def connect(self) -> None:
        """Open serial connection."""
        try:
            self._serial = serial.serial_for_url(
                self._url, baudrate=BAUD_RATE, timeout=self._timeout
            )
        except Exception as err:
            raise RadioRAConnectionError(f"Connect failed: {err}") from err

    def read_line(self, timeout: float | None = None) -> str | None:
        """Read one CR-terminated line. Returns None on timeout."""
        if self._serial is None:
            raise RadioRAConnectionLost("Not connected")

        old_timeout = self._serial.timeout
        if timeout is not None:
            self._serial.timeout = timeout

        try:
            data = self._serial.read_until(b"\r")
        except Exception as err:
            raise RadioRAConnectionLost(f"Read failed: {err}") from err
        finally:
            if timeout is not None:
                self._serial.timeout = old_timeout

        if not data:
            return None
        return data.decode(ENCODING, errors="replace").strip()

    def write(self, data: str) -> None:
        """Write a command string (CR is appended)."""
        if self._serial is None:
            raise RadioRAConnectionLost("Not connected")
        try:
            self._serial.write((data + "\r").encode(ENCODING))
            self._serial.flush()
        except Exception as err:
            raise RadioRAConnectionLost(f"Write failed: {err}") from err

    def close(self) -> None:
        """Close serial connection."""
        if self._serial:
            try:
                self._serial.close()
            except OSError:
                pass
            self._serial = None

    @property
    def connected(self) -> bool:
        """Whether serial port is open."""
        return self._serial is not None and self._serial.is_open
