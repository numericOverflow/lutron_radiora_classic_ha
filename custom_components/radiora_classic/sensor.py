"""Sensor platform for RadioRA Classic connection health (diagnostic)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
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
    """Set up RadioRA Classic connection health sensor."""
    data = entry.runtime_data
    coordinator = data.coordinator
    controller_id = entry.options["controller_id"]

    async_add_entities([RadioRAConnectionSensor(coordinator, controller_id)])


class RadioRAConnectionSensor(CoordinatorEntity[RadioRACoordinator], SensorEntity):
    """Diagnostic sensor showing connection health."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: RadioRACoordinator,
        controller_id: str,
    ) -> None:
        """Initialize the connection sensor."""
        super().__init__(coordinator)

        self._attr_unique_id = f"radiora_classic.{controller_id}.sensor.connection"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}.controller")},
            name=f"RadioRA Classic ({controller_id})",
            manufacturer="Lutron",
            model="RA-RS232",
            sw_version=coordinator.firmware_version,
        )

    @property
    def native_value(self) -> str:
        """Return connection state."""
        return "connected" if self.coordinator.connected else "disconnected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional diagnostic attributes."""
        return {
            "reconnect_count": self.coordinator.reconnect_count,
            "url": self.coordinator.url,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
