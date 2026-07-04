"""Async client for Lutron RadioRA Classic RS-232 control.

Primary client. Full-featured: auto-reconnect, monitoring callbacks, state cache.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone

from . import commands
from .const import (
    ENCODING,
    ButtonState,
    MonitorType,
    SwitchState,
    System,
)
from .exceptions import RadioRAConnectionLost, RadioRATimeoutError
from .messages import (
    AnyMessage,
    LEDMap,
    LocalZoneChange,
    MasterButtonPress,
    PromptReady,
    VersionInfo,
    ZoneMap,
)
from .protocol import MessageParser
from .transport import AsyncTransport

_LOGGER = logging.getLogger(__name__)

_RECONNECT_MIN_DELAY = 1.0
_RECONNECT_MAX_DELAY = 60.0
_DEFAULT_POLL_INTERVAL = 30.0
_RESPONSE_TIMEOUT = 5.0


class RadioRAClient:
    """Async client for Lutron RadioRA Classic RS-232 control.

    URL schemes:
    - 'socket://host:port' — Raw TCP. For ser2net in raw TCP mode, or
                             FakeRadioRAController in tests.
    - 'rfc2217://host:port' — RFC 2217 (telnet serial port control).
    - '/dev/ttyUSB0'        — Direct local serial via pyserial-asyncio-fast.
    """

    def __init__(
        self,
        url: str,
        callback: Callable[[AnyMessage], None] | None = None,
        bridged: bool = False,
    ) -> None:
        self._url = url
        self._callback = callback
        self._bridged = bridged
        self._transport: AsyncTransport | None = None
        self._parser = MessageParser()
        self._read_task: asyncio.Task[None] | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._reconnect_delay = _RECONNECT_MIN_DELAY
        self._stopping = False

        # State cache
        self._zone_states: dict[tuple[System, int], bool | None] = {}
        self._phantom_led_states: dict[int, bool] = {}

        # Health tracking
        self._connected_at: datetime | None = None
        self._last_message_at: datetime | None = None
        self._reconnect_count = 0

        # Response waiters (type, future) — only messages matching the type resolve the future
        self._response_waiters: list[tuple[type, asyncio.Future[AnyMessage]]] = []

        # Command sequencing: device ignores input until it sends '!' prompt
        self._cmd_lock: asyncio.Lock = asyncio.Lock()
        self._prompt_ready: asyncio.Event = asyncio.Event()
        self._prompt_ready.set()  # Assume ready initially (first cmd after connect)

    # --- Connection Lifecycle ---

    async def connect(self) -> None:
        """Connect to the RA-RS232 interface."""
        self._transport = await AsyncTransport.connect(self._url)
        self._connected_at = datetime.now(timezone.utc)
        self._parser.reset()
        self._prompt_ready.set()  # Assume ready for first command after connect

    async def disconnect(self) -> None:
        """Disconnect and stop all background tasks."""
        self._stopping = True
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        if self._transport:
            await self._transport.close()
            self._transport = None

    async def start(self) -> None:
        """Connect + start read loop + enable monitoring.

        This is the typical entry point for long-running consumers (HA).
        Automatically reconnects on connection loss.
        """
        self._stopping = False
        await self.connect()
        self._read_task = asyncio.create_task(self._read_loop())
        await self._enable_prompts()
        await self.start_monitoring()
        await self._query_initial_state()

    async def stop(self) -> None:
        """Stop read loop, disable monitoring, disconnect."""
        self._stopping = True
        await self.stop_polling()
        try:
            await self.stop_monitoring()
        except (RadioRAConnectionLost, OSError):
            pass
        await self.disconnect()

    @property
    def connected(self) -> bool:
        """True if transport is connected."""
        return self._transport is not None and self._transport.connected

    @property
    def url(self) -> str:
        """Connection URL."""
        return self._url

    # --- Zone Control ---

    async def set_dimmer_level(
        self,
        zone: int,
        level: int,
        fade_sec: int | None = None,
        system: System = System.NONE,
    ) -> None:
        """Set dimmer to level (0-100)."""
        cmd = commands.set_dimmer_level(zone, level, fade_sec, system)
        await self._send(cmd)

    async def switch_on(
        self,
        zone: int,
        delay_sec: int | None = None,
        system: System = System.NONE,
    ) -> None:
        """Turn switch zone ON."""
        cmd = commands.set_switch_level(zone, SwitchState.ON, delay_sec, system)
        await self._send(cmd)

    async def switch_off(
        self,
        zone: int,
        delay_sec: int | None = None,
        system: System = System.NONE,
    ) -> None:
        """Turn switch zone OFF."""
        cmd = commands.set_switch_level(zone, SwitchState.OFF, delay_sec, system)
        await self._send(cmd)

    # --- Phantom Buttons ---

    async def button_press(
        self,
        button: int,
        state: ButtonState = ButtonState.ON,
        fade_sec: int | None = None,
        system: System = System.NONE,
    ) -> None:
        """Press a phantom button (1-15) or system button (16=ALL ON, 17=ALL OFF)."""
        cmd = commands.button_press(button, state, fade_sec, system)
        await self._send(cmd)

    async def raise_button(self, button: int, system: System = System.NONE) -> None:
        """Start raise-ramp on phantom button (hold behavior)."""
        cmd = commands.raise_button(button, system)
        await self._send(cmd)

    async def lower_button(self, button: int, system: System = System.NONE) -> None:
        """Start lower-ramp on phantom button (hold behavior)."""
        cmd = commands.lower_button(button, system)
        await self._send(cmd)

    async def stop_raise_lower(self) -> None:
        """Stop any active raise/lower ramp."""
        await self._send(commands.stop_raise_lower())

    # --- State Queries ---

    async def get_zone_map(self) -> list[ZoneMap]:
        """Send ZMPI, collect response(s), return them.

        Returns:
            List of 1 ZoneMap (single system) or 2 ZoneMaps (bridged: S1 + S2).
        """
        expected_count = 2 if self._bridged else 1
        await self._send(commands.zone_map_inquiry())

        results: list[ZoneMap] = []
        deadline = asyncio.get_event_loop().time() + _RESPONSE_TIMEOUT

        while len(results) < expected_count:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            msg = await self._wait_for_message(ZoneMap, timeout=remaining)
            if msg is not None:
                results.append(msg)
            else:
                break

        if not results:
            raise RadioRATimeoutError("No ZMP response received for ZMPI")
        return results

    async def get_led_map(self) -> LEDMap:
        """Query current state of all 15 phantom button LEDs."""
        await self._send(commands.phantom_led_status())
        msg = await self._wait_for_message(LEDMap, timeout=_RESPONSE_TIMEOUT)
        if msg is None:
            raise RadioRATimeoutError("No LMP response received")
        return msg

    async def get_version(self) -> VersionInfo:
        """Query firmware version (VERI command)."""
        await self._send(commands.version_inquiry())
        msg = await self._wait_for_message(VersionInfo, timeout=_RESPONSE_TIMEOUT)
        if msg is None:
            raise RadioRATimeoutError("No REV response received")
        return msg

    # --- Monitoring ---

    async def start_monitoring(self) -> None:
        """Enable all monitoring. Fire-and-forget — no response expected."""
        await self._send(commands.enable_monitoring(MonitorType.ZONE_CHANGE))
        await self._send(commands.enable_monitoring(MonitorType.BUTTON_PRESS))
        await self._send(commands.enable_monitoring(MonitorType.ZONE_MAP))

    async def stop_monitoring(self) -> None:
        """Disable all monitoring."""
        await self._send(commands.disable_monitoring(MonitorType.ZONE_CHANGE))
        await self._send(commands.disable_monitoring(MonitorType.BUTTON_PRESS))
        await self._send(commands.disable_monitoring(MonitorType.ZONE_MAP))

    # --- State Cache ---

    @property
    def zone_states(self) -> dict[tuple[System, int], bool | None]:
        """Cached zone on/off states (updated by monitoring + polling)."""
        return dict(self._zone_states)

    @property
    def phantom_led_states(self) -> dict[int, bool]:
        """Cached phantom button LED states."""
        return dict(self._phantom_led_states)

    # --- Health ---

    @property
    def connected_at(self) -> datetime | None:
        """Timestamp of last successful connection."""
        return self._connected_at

    @property
    def last_message_at(self) -> datetime | None:
        """Timestamp of last received message."""
        return self._last_message_at

    @property
    def reconnect_count(self) -> int:
        """Number of reconnections since start()."""
        return self._reconnect_count

    # --- Polling ---

    async def start_polling(self, interval_sec: float = _DEFAULT_POLL_INTERVAL) -> None:
        """Start periodic ZMPI polling as heartbeat/reconciliation."""
        if self._poll_task and not self._poll_task.done():
            return
        self._poll_task = asyncio.create_task(self._poll_loop(interval_sec))

    async def stop_polling(self) -> None:
        """Stop periodic polling."""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

    # --- Internals ---

    async def _enable_prompts(self) -> None:
        """Send PON to ensure '!' prompts are enabled.

        This is a bootstrap command -- we bypass _send() because prompts
        may not yet be enabled (so we can't gate on a prompt that might
        not exist). After PON is processed, the device will send '!' for
        all subsequent commands.
        """
        if not self._transport or not self._transport.connected:
            return
        _LOGGER.debug("TX: PON (bootstrap)")
        await self._transport.write(b"PON\r")
        # Wait briefly for the device to process and send '!'
        # If prompts were already on, we get '!' back. If they were off,
        # PON enables them but this particular command may not get one.
        # Either way, give the read loop time to pick up the banner + prompt.
        try:
            await asyncio.wait_for(self._prompt_ready.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            # No prompt received -- that's OK, prompts are now enabled
            # for subsequent commands. Set ready so first _send() proceeds.
            self._prompt_ready.set()
            _LOGGER.debug("No prompt after PON (expected if prompts were off)")

    async def _send(self, cmd: str) -> None:
        """Wait for device ready, then send command.

        Per spec 044-038a: the device ignores all input until it issues
        the '!' prompt from the previous command. We gate writes on the
        prompt and serialize with a lock. Returns immediately after sending
        (does NOT wait for this command's '!' -- that gates the NEXT send).
        """
        if not self._transport or not self._transport.connected:
            raise RadioRAConnectionLost("Not connected")
        async with self._cmd_lock:
            # Wait for device to be ready (! from previous command)
            try:
                await asyncio.wait_for(self._prompt_ready.wait(), timeout=_RESPONSE_TIMEOUT)
            except asyncio.TimeoutError:
                _LOGGER.debug("Prompt not ready before send: %s (proceeding anyway)", cmd)
            self._prompt_ready.clear()
            _LOGGER.debug("TX: %s", cmd)
            await self._transport.write((cmd + "\r").encode(ENCODING))

    async def _read_loop(self) -> None:
        """Background task: continuously read and dispatch messages."""
        while not self._stopping:
            try:
                if not self._transport or not self._transport.connected:
                    break
                data = await self._transport.readline()
                _LOGGER.debug("RX: %s", data.decode("ascii", errors="replace").strip())
                messages = self._parser.feed(data)
                for msg in messages:
                    self._last_message_at = msg.timestamp
                    if isinstance(msg, PromptReady):
                        # Signal command sequencing - don't dispatch to callback
                        self._prompt_ready.set()
                        continue
                    self._update_cache(msg)
                    self._resolve_waiters(msg)
                    if self._callback:
                        try:
                            self._callback(msg)
                        except Exception:
                            _LOGGER.exception("Callback error")
            except RadioRAConnectionLost:
                if not self._stopping:
                    _LOGGER.warning("Connection lost, scheduling reconnect")
                    self._schedule_reconnect()
                break
            except asyncio.CancelledError:
                break

    def _update_cache(self, msg: AnyMessage) -> None:
        """Update internal state cache from received message."""
        if isinstance(msg, LocalZoneChange):
            from .const import ZoneState

            key = (msg.system, msg.zone)
            if msg.state == ZoneState.OFF:
                self._zone_states[key] = False
            else:
                self._zone_states[key] = True
        elif isinstance(msg, ZoneMap):
            for i, ch in enumerate(msg.states, start=1):
                key = (msg.system, i)
                if ch == "X":
                    self._zone_states[key] = None
                elif ch == "1":
                    self._zone_states[key] = True
                else:
                    self._zone_states[key] = False
        elif isinstance(msg, LEDMap):
            for i, ch in enumerate(msg.bitmap, start=1):
                self._phantom_led_states[i] = ch == "1"

    def _resolve_waiters(self, msg: AnyMessage) -> None:
        """Resolve the first pending waiter whose expected type matches this message."""
        resolved: list[tuple[type, asyncio.Future[AnyMessage]]] = []
        for expected_type, fut in self._response_waiters:
            if not fut.done() and isinstance(msg, expected_type):
                fut.set_result(msg)
                resolved.append((expected_type, fut))
                break  # resolve one at a time
        for item in resolved:
            self._response_waiters.remove(item)

    @property
    def _read_loop_active(self) -> bool:
        """True if the background read loop is running."""
        return self._read_task is not None and not self._read_task.done()

    async def _wait_for_message(
        self, msg_type: type, timeout: float = _RESPONSE_TIMEOUT
    ) -> AnyMessage | None:
        """Wait for a specific message type.

        If the background read loop is active, registers a typed future that
        the read loop will resolve. If no read loop is running (simple
        connect + query usage), reads inline from the transport directly.
        This ensures request/response methods like get_zone_map() work
        regardless of whether start() was called.
        """
        if self._read_loop_active:
            # Read loop is running — register a typed future for it to resolve
            fut: asyncio.Future[AnyMessage] = asyncio.get_event_loop().create_future()
            self._response_waiters.append((msg_type, fut))
            try:
                return await asyncio.wait_for(fut, timeout=timeout)
            except asyncio.TimeoutError:
                return None
            finally:
                entry = (msg_type, fut)
                if entry in self._response_waiters:
                    self._response_waiters.remove(entry)
        else:
            # No read loop — read inline from transport until we get the type we want
            deadline = asyncio.get_event_loop().time() + timeout
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    return None
                if not self._transport or not self._transport.connected:
                    return None
                try:
                    data = await asyncio.wait_for(
                        self._transport.readline(), timeout=remaining
                    )
                except asyncio.TimeoutError:
                    return None
                except RadioRAConnectionLost:
                    return None
                messages = self._parser.feed(data)
                for msg in messages:
                    self._last_message_at = msg.timestamp
                    if isinstance(msg, PromptReady):
                        self._prompt_ready.set()
                        continue
                    self._update_cache(msg)
                    if self._callback:
                        try:
                            self._callback(msg)
                        except Exception:
                            _LOGGER.exception("Callback error")
                    if isinstance(msg, msg_type):
                        return msg

    def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt."""
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Attempt reconnection with exponential backoff."""
        while not self._stopping:
            _LOGGER.info("Reconnecting in %.1fs...", self._reconnect_delay)
            await asyncio.sleep(self._reconnect_delay)
            try:
                if self._transport:
                    await self._transport.close()
                await self.connect()
                self._reconnect_count += 1
                self._reconnect_delay = _RECONNECT_MIN_DELAY
                _LOGGER.info("Reconnected successfully (count=%d)", self._reconnect_count)
                # Re-enable monitoring and restart read loop
                self._read_task = asyncio.create_task(self._read_loop())
                await self._enable_prompts()
                await self.start_monitoring()
                await self._query_initial_state()
                return
            except Exception:
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, _RECONNECT_MAX_DELAY
                )
                _LOGGER.warning(
                    "Reconnect failed, next attempt in %.1fs", self._reconnect_delay
                )

    async def _query_initial_state(self) -> None:
        """Query full zone/LED state on connect."""
        try:
            zone_maps = await self.get_zone_map()
            for zm in zone_maps:
                self._update_cache(zm)
        except (RadioRATimeoutError, RadioRAConnectionLost):
            _LOGGER.warning("Initial state query failed")

    async def _poll_loop(self, interval: float) -> None:
        """Periodic ZMPI polling for heartbeat/reconciliation."""
        while not self._stopping:
            await asyncio.sleep(interval)
            if self._stopping:
                break
            try:
                zone_maps = await self.get_zone_map()
                for zm in zone_maps:
                    self._update_cache(zm)
            except (RadioRATimeoutError, RadioRAConnectionLost):
                _LOGGER.debug("Poll failed — connection may be lost")
            except asyncio.CancelledError:
                break
