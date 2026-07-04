"""DataUpdateCoordinator for RadioRA Classic integration.

Push+poll hybrid: push messages update state immediately via
async_set_updated_data(); periodic ZMPI poll reconciles state
and serves as a heartbeat.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import RadioRAClientWrapper
from .pyradiora_classic import (
    AnyMessage,
    ButtonState,
    LEDMap,
    LocalZoneChange,
    MasterButtonPress,
    RadioRAConnectionError,
    RadioRAConnectionLost,
    RadioRATimeoutError,
    System,
    ZoneMap,
    ZoneState,
)

_LOGGER = logging.getLogger(__name__)


class RadioRACoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for RadioRA Classic push+poll hybrid."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        url: str,
        bridged: bool,
        controller_id: str,
        poll_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"RadioRA Classic {controller_id}",
            update_interval=timedelta(seconds=poll_interval) if poll_interval > 0 else None,
        )
        self._url = url
        self._bridged = bridged
        self._controller_id = controller_id
        self._client = RadioRAClientWrapper(url, bridged, self._handle_message)

        # State caches
        self._zone_levels: dict[tuple[System, int], int] = {}
        self._phantom_states: dict[int, bool] = {}
        self._master_events: dict[tuple[int, int], datetime] = {}

    # --- Properties ---

    @property
    def connected(self) -> bool:
        """Whether the RS-232 connection is active."""
        return self._client.connected

    @property
    def reconnect_count(self) -> int:
        """Number of reconnections since entry load."""
        return self._client.reconnect_count

    @property
    def url(self) -> str:
        """Connection URL for diagnostics."""
        return self._url

    @property
    def controller_id(self) -> str:
        """Controller identifier."""
        return self._controller_id

    # --- Entity API ---

    async def async_set_dimmer(
        self, zone: int, level: int, fade_sec: int | None, system: System
    ) -> None:
        """Set dimmer level. Called by light entities."""
        # Optimistic update — assume command will succeed
        self._zone_levels[(system, zone)] = level
        self.async_set_updated_data(self._build_state_snapshot())
        # Send command (fire-and-forget)
        await self._client.set_dimmer_level(zone, level, fade_sec, system)

    async def async_switch_zone(self, zone: int, on: bool, system: System) -> None:
        """Turn switch zone on/off. Called by light entities in ONOFF mode."""
        self._zone_levels[(system, zone)] = 100 if on else 0
        self.async_set_updated_data(self._build_state_snapshot())
        if on:
            await self._client.switch_on(zone, system)
        else:
            await self._client.switch_off(zone, system)

    async def async_press_phantom(
        self, button: int, state: ButtonState, system: System
    ) -> None:
        """Press phantom button. Called by switch entities."""
        # Optimistic update for phantom switches
        self._phantom_states[button] = state == ButtonState.ON
        self.async_set_updated_data(self._build_state_snapshot())
        await self._client.button_press(button, state, system)

    async def async_send_raw(self, command: str) -> None:
        """Send a raw RS-232 command (debug service)."""
        await self._client.send_raw(command)

    def get_zone_level(self, zone: int, system: System = System.NONE) -> int:
        """Get cached zone brightness level (0-100)."""
        return self._zone_levels.get((system, zone), 0)

    def get_phantom_state(self, button: int) -> bool:
        """Get cached phantom button LED state."""
        return self._phantom_states.get(button, False)

    def get_master_last_press(self, master: int, button: int) -> datetime | None:
        """Get timestamp of last master button press."""
        return self._master_events.get((master, button))

    # --- DataUpdateCoordinator interface ---

    async def _async_update_data(self) -> dict[str, Any]:
        """Called by DataUpdateCoordinator on each poll interval.

        Lazy connect on first call or after disconnect.
        """
        try:
            if not self._client.connected:
                await self._client.start()

            # Query zone map (reconciliation heartbeat)
            zone_maps = await self._client.get_zone_map()
            for zm in zone_maps:
                self._handle_zone_map(zm)

            # Query phantom LED states (non-fatal if unsupported/no phantoms)
            try:
                led_map = await self._client.get_led_map()
                self._handle_led_map(led_map)
            except RadioRATimeoutError:
                _LOGGER.debug("LMP query timed out (no phantom buttons configured?)")

        except RadioRAConnectionError as err:
            raise ConfigEntryNotReady(
                f"Cannot connect to RadioRA Classic at {self._url}: {err}"
            ) from err
        except (RadioRATimeoutError, RadioRAConnectionLost) as err:
            raise UpdateFailed(f"Communication error: {err}") from err

        return self._build_state_snapshot()

    async def async_shutdown(self) -> None:
        """Called by HA on entry unload or stop."""
        await super().async_shutdown()
        await self._client.stop()

    # --- Push Message Handling ---

    @callback
    def _handle_message(self, msg: AnyMessage) -> None:
        """Route incoming push messages to appropriate cache updates."""
        if isinstance(msg, LocalZoneChange):
            self._handle_zone_change(msg)
        elif isinstance(msg, ZoneMap):
            self._handle_zone_map(msg)
            self.async_set_updated_data(self._build_state_snapshot())
        elif isinstance(msg, LEDMap):
            self._handle_led_map(msg)
            self.async_set_updated_data(self._build_state_snapshot())
        elif isinstance(msg, MasterButtonPress):
            self._handle_master_press(msg)

    def _handle_zone_change(self, msg: LocalZoneChange) -> None:
        """LZC push — a zone changed locally."""
        key = (msg.system, msg.zone)
        if msg.state == ZoneState.OFF:
            self._zone_levels[key] = 0
        elif msg.state == ZoneState.ON:
            self._zone_levels[key] = 100
        # CHG = changed but unknown level — keep last-known level.
        # Protocol has no command to query exact dimmer level.
        # Zone stays marked as ON with its previous brightness.
        self.async_set_updated_data(self._build_state_snapshot())

    def _handle_zone_map(self, msg: ZoneMap) -> None:
        """ZMP response — full 32-zone bitmap.

        ZMP only reports ON/OFF (binary). To avoid clobbering accurate
        dimmer levels from optimistic updates, we only overwrite when:
        - Zone turned OFF (level -> 0)
        - Zone is ON but has no tracked level yet (first poll / restart)
        """
        for zone_num in range(1, 33):
            is_on = msg.is_zone_on(zone_num)
            key = (msg.system, zone_num)
            if is_on is None:
                continue  # unassigned zone
            if not is_on:
                self._zone_levels[key] = 0
            elif key not in self._zone_levels or self._zone_levels[key] == 0:
                # Zone is ON but we have no tracked level — assume 100%
                self._zone_levels[key] = 100
            # else: zone is ON and we already have a tracked level — preserve it

    def _handle_led_map(self, msg: LEDMap) -> None:
        """LMP response — phantom button LED states."""
        for btn in range(1, 16):
            self._phantom_states[btn] = msg.is_button_active(btn)

    def _handle_master_press(self, msg: MasterButtonPress) -> None:
        """MBP push — master control button pressed."""
        key = (msg.master_control, msg.button)
        self._master_events[key] = msg.timestamp
        self.async_set_updated_data(self._build_state_snapshot())

    # --- Internal ---

    def _build_state_snapshot(self) -> dict[str, Any]:
        """Build coordinator data dict.

        Entities use getter methods, but async_set_updated_data() requires
        a non-None payload to trigger entity updates.
        """
        return {
            "zone_levels": dict(self._zone_levels),
            "phantom_states": dict(self._phantom_states),
            "master_events": dict(self._master_events),
        }
