"""Lutron RadioRA Classic integration."""

from __future__ import annotations

import logging

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_BRIDGED,
    CONF_CONTROLLER_ID,
    CONF_POLL_INTERVAL,
    CONF_URL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .coordinator import RadioRACoordinator
from .models import RadioRAConfigEntry, RadioRAData

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: RadioRAConfigEntry) -> bool:
    """Set up RadioRA Classic from a config entry."""
    url = entry.data[CONF_URL]
    bridged = entry.data.get(CONF_BRIDGED, False)
    controller_id = entry.options[CONF_CONTROLLER_ID]
    poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)

    coordinator = RadioRACoordinator(
        hass, entry, url, bridged, controller_id, poll_interval
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = RadioRAData(coordinator=coordinator, controller_id=controller_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register shutdown listener
    async def _shutdown(event: object) -> None:
        await coordinator.async_shutdown()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown)
    )

    # Reload entry when options change (zone add/remove, settings change)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    # Register services (only once, on first entry)
    if not hass.services.has_service(DOMAIN, "send_command"):
        _register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: RadioRAConfigEntry) -> bool:
    """Unload a config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.coordinator.async_shutdown()
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: RadioRAConfigEntry
) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _get_coordinator(hass: HomeAssistant, controller_id: str) -> RadioRACoordinator:
    """Find coordinator by controller_id across all config entries."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if (
            entry.runtime_data
            and entry.runtime_data.controller_id == controller_id
        ):
            return entry.runtime_data.coordinator
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="controller_not_found",
        translation_placeholders={"controller_id": controller_id},
    )


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def async_send_command(call: ServiceCall) -> None:
        controller_id = call.data["controller_id"]
        command = call.data["command"]
        coordinator = _get_coordinator(hass, controller_id)
        await coordinator.async_send_raw(command)

    async def async_export_config(call: ServiceCall) -> None:
        controller_id = call.data["controller_id"]
        entry = _get_entry_by_controller(hass, controller_id)
        csv_content = _build_csv_export(entry.options)
        path = hass.config.path(f"radiora_classic_{controller_id}_export.csv")
        await hass.async_add_executor_job(_write_file, path, csv_content)
        hass.components.persistent_notification.async_create(
            f"Config exported to `{path}`",
            title="RadioRA Classic Export",
        )

    hass.services.async_register(DOMAIN, "send_command", async_send_command)
    hass.services.async_register(DOMAIN, "export_config", async_export_config)


def _get_entry_by_controller(
    hass: HomeAssistant, controller_id: str
) -> RadioRAConfigEntry:
    """Find config entry by controller_id."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if (
            entry.runtime_data
            and entry.runtime_data.controller_id == controller_id
        ):
            return entry  # type: ignore[return-value]
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="controller_not_found",
        translation_placeholders={"controller_id": controller_id},
    )


def _build_csv_export(options: dict) -> str:
    """Build CSV string from current config options."""
    import csv
    from io import StringIO

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["type", "number", "name", "mode", "area", "system", "fade_sec"])

    for zone in options.get("zones", []):
        writer.writerow([
            "zone",
            zone["zone"],
            zone["name"],
            zone.get("mode", "dimmer"),
            zone.get("area", ""),
            zone.get("system", ""),
            zone.get("fade_sec") or "",
        ])
    for btn in options.get("phantom_buttons", []):
        writer.writerow([
            "phantom",
            btn["button"],
            btn["name"],
            "",
            btn.get("area", ""),
            "",
            "",
        ])
    for mc in options.get("master_controls", []):
        writer.writerow([
            "master",
            f"{mc['master_control']}:{mc['button']}",
            mc["name"],
            "",
            mc.get("area", ""),
            "",
            "",
        ])

    return output.getvalue()


def _write_file(path: str, content: str) -> None:
    """Write content to file (executed in executor)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
