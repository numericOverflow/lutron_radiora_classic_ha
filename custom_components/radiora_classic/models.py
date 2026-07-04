"""Data models and type aliases for RadioRA Classic integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

if TYPE_CHECKING:
    from .coordinator import RadioRACoordinator


@dataclass(slots=True)
class RadioRAData:
    """Runtime data stored in entry.runtime_data."""

    coordinator: RadioRACoordinator
    controller_id: str


type RadioRAConfigEntry = ConfigEntry[RadioRAData]
