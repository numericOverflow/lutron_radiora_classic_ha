"""Light platform for RadioRA Classic zones."""

from __future__ import annotations

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RadioRACoordinator
from .models import RadioRAConfigEntry
from .pyradiora_classic import System


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RadioRAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up RadioRA Classic light entities."""
    data = entry.runtime_data
    coordinator = data.coordinator
    controller_id = entry.options["controller_id"]

    entities = [
        RadioRALight(coordinator, controller_id, zone_config)
        for zone_config in entry.options.get("zones", [])
    ]
    async_add_entities(entities)


class RadioRALight(CoordinatorEntity[RadioRACoordinator], LightEntity):
    """A RadioRA Classic zone as a light entity.

    Supports both BRIGHTNESS (dimmer) and ONOFF modes based on user config.
    """

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        coordinator: RadioRACoordinator,
        controller_id: str,
        zone_config: dict,
    ) -> None:
        """Initialize the light entity."""
        super().__init__(coordinator)
        self._zone: int = zone_config["zone"]
        self._system = System(zone_config["system"]) if "system" in zone_config else System.NONE
        self._fade_sec: int | None = zone_config.get("fade_sec")
        self._mode: str = zone_config.get("mode", "dimmer")
        self._prev_level: int = 100  # last non-zero brightness for restore on turn_on

        # ColorMode based on user config
        if self._mode == "onoff":
            self._attr_color_mode = ColorMode.ONOFF
            self._attr_supported_color_modes = {ColorMode.ONOFF}
        else:
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

        # Entity identification
        system_prefix = f"s{self._system.value}." if self._system != System.NONE else ""
        self._attr_unique_id = f"radiora_classic.{controller_id}.{system_prefix}light.z{self._zone}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}.{system_prefix}light.z{self._zone}")},
            name=zone_config["name"],
            manufacturer="Lutron",
            model="RadioRA Classic Zone",
        )
        if zone_config.get("area"):
            self._attr_device_info["suggested_area"] = zone_config["area"]

    @property
    def brightness(self) -> int | None:
        """Return current brightness (0-255 scale)."""
        if self._mode == "onoff":
            return None
        level = self.coordinator.get_zone_level(self._zone, self._system)
        return int(level * 255 / 100)

    @property
    def is_on(self) -> bool:
        """Return true if zone is on."""
        return self.coordinator.get_zone_level(self._zone, self._system) > 0

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the zone on."""
        if self._mode == "onoff":
            # SSL command — no fade parameter supported
            await self.coordinator.async_switch_zone(self._zone, True, self._system)
            return

        # Resolve fade: explicit transition kwarg > per-zone config > None (omit)
        fade = self._resolve_fade(kwargs)

        if ATTR_BRIGHTNESS in kwargs:
            level = int(kwargs[ATTR_BRIGHTNESS] * 100 / 255)
            self._prev_level = level
            await self.coordinator.async_set_dimmer(self._zone, level, fade, self._system)
        else:
            # Restore previous brightness (not always 100%)
            await self.coordinator.async_set_dimmer(
                self._zone, self._prev_level, fade, self._system
            )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the zone off."""
        # Preserve current level for restore on next turn_on
        current = self.coordinator.get_zone_level(self._zone, self._system)
        if current > 0:
            self._prev_level = current

        if self._mode == "onoff":
            # SSL command — no fade parameter supported
            await self.coordinator.async_switch_zone(self._zone, False, self._system)
            return

        fade = self._resolve_fade(kwargs)
        await self.coordinator.async_set_dimmer(self._zone, 0, fade, self._system)

    def _resolve_fade(self, kwargs: dict) -> int | None:
        """Resolve fade time: explicit transition > zone config > None."""
        transition = kwargs.get(ATTR_TRANSITION)
        if transition is not None:
            return int(transition)
        return self._fade_sec

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
