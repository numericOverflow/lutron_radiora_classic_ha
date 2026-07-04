"""Button platform for RadioRA Classic system buttons (ALL ON / ALL OFF)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RadioRACoordinator
from .models import RadioRAConfigEntry
from .pyradiora_classic import BUTTON_ALL_OFF, BUTTON_ALL_ON, ButtonState, System


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RadioRAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up RadioRA Classic system button entities (always 2)."""
    data = entry.runtime_data
    coordinator = data.coordinator
    controller_id = entry.options["controller_id"]

    async_add_entities([
        RadioRASystemButton(coordinator, controller_id, BUTTON_ALL_ON, "All On"),
        RadioRASystemButton(coordinator, controller_id, BUTTON_ALL_OFF, "All Off"),
    ])


class RadioRASystemButton(CoordinatorEntity[RadioRACoordinator], ButtonEntity):
    """A RadioRA Classic system button (ALL ON = 16, ALL OFF = 17).

    Stateless press actions — no feedback, just fires the command.
    """

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        coordinator: RadioRACoordinator,
        controller_id: str,
        button_num: int,
        name: str,
    ) -> None:
        """Initialize the system button."""
        super().__init__(coordinator)
        self._button = button_num
        slug = "all_on" if button_num == BUTTON_ALL_ON else "all_off"

        self._attr_unique_id = f"radiora_classic.{controller_id}.button.{slug}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}.button.{slug}")},
            name=name,
            manufacturer="Lutron",
            model="RadioRA Classic System Button",
        )

    async def async_press(self) -> None:
        """Press the system button."""
        state = ButtonState.ON if self._button == BUTTON_ALL_ON else ButtonState.OFF
        await self.coordinator.async_press_phantom(self._button, state, System.NONE)
