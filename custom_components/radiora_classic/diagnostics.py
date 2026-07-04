"""Diagnostics for RadioRA Classic integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .models import RadioRAConfigEntry

TO_REDACT = {"url"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RadioRAConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    coordinator = data.coordinator

    return async_redact_data(
        {
            "entry_data": dict(entry.data),
            "entry_options": dict(entry.options),
            "state": {
                "connected": coordinator.connected,
                "reconnect_count": coordinator.reconnect_count,
                "zone_count": len(entry.options.get("zones", [])),
                "phantom_count": len(entry.options.get("phantom_buttons", [])),
                "master_count": len(entry.options.get("master_controls", [])),
                "zone_levels": {
                    f"z{z}": coordinator.get_zone_level(z)
                    for z in range(1, 33)
                    if coordinator.get_zone_level(z) > 0
                },
                "phantom_states": {
                    f"b{b}": coordinator.get_phantom_state(b)
                    for b in range(1, 16)
                },
            },
        },
        TO_REDACT,
    )
