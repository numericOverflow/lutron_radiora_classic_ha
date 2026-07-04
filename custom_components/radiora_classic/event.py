"""Event platform for RadioRA Classic master control button presses."""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RadioRACoordinator
from .models import RadioRAConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RadioRAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up RadioRA Classic master control event entities."""
    data = entry.runtime_data
    coordinator = data.coordinator
    controller_id = entry.options["controller_id"]

    entities = [
        RadioRAMasterEvent(coordinator, controller_id, mc_config)
        for mc_config in entry.options.get("master_controls", [])
    ]
    async_add_entities(entities)


class RadioRAMasterEvent(CoordinatorEntity[RadioRACoordinator], EventEntity):
    """A RadioRA Classic master control button as an event entity.

    Fires a 'press' event when an MBP message is received.
    """

    _attr_has_entity_name = True
    _attr_name = None
    _attr_event_types = ["press"]

    def __init__(
        self,
        coordinator: RadioRACoordinator,
        controller_id: str,
        mc_config: dict,
    ) -> None:
        """Initialize the master control event entity."""
        super().__init__(coordinator)
        self._master: int = mc_config["master_control"]
        self._button: int = mc_config["button"]

        self._attr_unique_id = (
            f"radiora_classic.{controller_id}.master.mc{self._master}.b{self._button}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, f"{controller_id}.master.mc{self._master}.b{self._button}")
            },
            name=mc_config["name"],
            manufacturer="Lutron",
            model="RadioRA Classic Master Control",
        )
        if mc_config.get("area"):
            self._attr_device_info["suggested_area"] = mc_config["area"]

        self._last_seen_ts: datetime | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Check if this master button was just pressed and fire event."""
        ts = self.coordinator.get_master_last_press(self._master, self._button)
        if ts is not None and ts != self._last_seen_ts:
            # New press detected
            self._last_seen_ts = ts
            self._trigger_event("press")
            self.async_write_ha_state()
