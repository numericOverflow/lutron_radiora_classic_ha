"""HA-layer wrapper around pyradiora_classic.RadioRAClient.

Single import point for the bundled library. No other integration file
should import from .pyradiora_classic directly.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from .pyradiora_classic import (
    AnyMessage,
    ButtonState,
    LEDMap,
    RadioRAClient,
    RadioRAConnectionError,
    RadioRAConnectionLost,
    RadioRATimeoutError,
    System,
    VersionInfo,
    ZoneMap,
)

_LOGGER = logging.getLogger(__name__)


class RadioRAClientWrapper:
    """HA-layer wrapper around pyradiora_classic.RadioRAClient.

    Responsibilities:
    - Single point of contact with the bundled library
    - Callback bridging (library -> coordinator)
    - Future-proofing for PyPI migration (only this file changes)
    """

    def __init__(
        self,
        url: str,
        bridged: bool,
        message_callback: Callable[[AnyMessage], None],
    ) -> None:
        self._client = RadioRAClient(
            url=url,
            callback=message_callback,
            bridged=bridged,
        )

    # --- Lifecycle ---

    async def connect(self) -> None:
        """Establish connection (no monitoring)."""
        await self._client.connect()

    async def start(self) -> None:
        """Connect + start read loop + enable monitoring + query initial state."""
        await self._client.start()

    async def stop(self) -> None:
        """Stop monitoring + disconnect."""
        await self._client.stop()

    async def disconnect(self) -> None:
        """Disconnect without stopping monitoring (for config flow test connections)."""
        await self._client.disconnect()

    async def start_polling(self, interval: float) -> None:
        """Start periodic ZMPI polling."""
        await self._client.start_polling(interval)

    async def stop_polling(self) -> None:
        """Stop periodic polling."""
        await self._client.stop_polling()

    # --- Commands (called by entities via coordinator) ---

    async def set_dimmer_level(
        self, zone: int, level: int, fade_sec: int | None, system: System
    ) -> None:
        """Set dimmer level (0-100)."""
        await self._client.set_dimmer_level(zone, level, fade_sec, system)

    async def switch_on(self, zone: int, system: System) -> None:
        """Turn switch zone ON."""
        await self._client.switch_on(zone, system=system)

    async def switch_off(self, zone: int, system: System) -> None:
        """Turn switch zone OFF."""
        await self._client.switch_off(zone, system=system)

    async def button_press(self, button: int, state: ButtonState, system: System) -> None:
        """Press a phantom button."""
        await self._client.button_press(button, state, system=system)

    async def send_raw(self, command: str) -> None:
        """Send a raw command string (for advanced/debug service)."""
        await self._client._send(command)  # noqa: SLF001

    # --- Queries (used by config flow + coordinator) ---

    async def get_zone_map(self) -> list[ZoneMap]:
        """Query zone map (ZMPI)."""
        return await self._client.get_zone_map()

    async def get_led_map(self) -> LEDMap:
        """Query phantom LED states (LMP)."""
        return await self._client.get_led_map()

    async def get_version(self) -> VersionInfo:
        """Query firmware version (VERI)."""
        return await self._client.get_version()

    # --- State (delegated from library's cache) ---

    @property
    def connected(self) -> bool:
        """Whether the RS-232 connection is active."""
        return self._client.connected

    @property
    def connected_at(self) -> datetime | None:
        """Timestamp of last successful connection."""
        return self._client.connected_at

    @property
    def last_message_at(self) -> datetime | None:
        """Timestamp of last received message."""
        return self._client.last_message_at

    @property
    def reconnect_count(self) -> int:
        """Number of reconnections since start()."""
        return self._client.reconnect_count
