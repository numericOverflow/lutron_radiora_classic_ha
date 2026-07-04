"""Switch platform for RadioRA Classic phantom buttons (1-15)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RadioRACoordinator
from .models import RadioRAConfigEntry
from .pyradiora_classic import ButtonState, System


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RadioRAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up RadioRA Classic phantom button switch entities."""
    data = entry.runtime_data
    coordinator = data.coordinator
    controller_id = entry.options["controller_id"]

    entities = [
        RadioRAPhantomSwitch(coordinator, controller_id, button_config)
        for button_config in entry.options.get("phantom_buttons", [])
    ]
    async_add_entities(entities)


class RadioRAPhantomSwitch(CoordinatorEntity[RadioRACoordinator], SwitchEntity):
    """A RadioRA Classic phantom button as a switch entity.

    LED state = is_on (scene active indicator).
    """

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        coordinator: RadioRACoordinator,
        controller_id: str,
        button_config: dict,
    ) -> None:
        """Initialize the phantom button switch."""
        super().__init__(coordinator)
        self._button: int = button_config["button"]

        self._attr_unique_id = (
            f"radiora_classic.{controller_id}.phantom.b{self._button}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}.phantom.b{self._button}")},
            name=button_config["name"],
            manufacturer="Lutron",
            model="RadioRA Classic Phantom Button",
        )
        if button_config.get("area"):
            self._attr_device_info["suggested_area"] = button_config["area"]

    @property
    def is_on(self) -> bool:
        """Return true if phantom button LED is active."""
        return self.coordinator.get_phantom_state(self._button)

    async def async_turn_on(self, **kwargs) -> None:
        """Press phantom button ON."""
        await self.coordinator.async_press_phantom(
            self._button, ButtonState.ON, System.NONE
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Press phantom button OFF."""
        await self.coordinator.async_press_phantom(
            self._button, ButtonState.OFF, System.NONE
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
