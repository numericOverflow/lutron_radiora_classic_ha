"""Config flow for RadioRA Classic integration."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    AreaSelector,
    AreaSelectorConfig,
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)
from homeassistant.util import slugify

from .const import (
    CONF_BRIDGED,
    CONF_CONTROLLER_ID,
    CONF_DEBUG_LOGGING,
    CONF_POLL_INTERVAL,
    CONF_URL,
    CONF_ZONES,
    CONF_PHANTOM_BUTTONS,
    CONF_MASTER_CONTROLS,
    DEFAULT_DEBUG_LOGGING,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_CSV_ROWS,
    MAX_CSV_SIZE,
)
from .pyradiora_classic import (
    RadioRAClient,
    RadioRAConnectionError,
    RadioRATimeoutError,
    System,
)

if TYPE_CHECKING:
    from .coordinator import RadioRACoordinator

_LOGGER = logging.getLogger(__name__)


async def _try_connection(url: str, bridged: bool) -> None:
    """Test connection to RA-RS232. Raises on failure."""
    client = RadioRAClient(url=url, bridged=bridged)
    try:
        await client.connect()
        await client.get_version()
    finally:
        await client.disconnect()


async def _flash_zone(url: str, zone: int, system: System = System.NONE, duration: int = 5) -> None:
    """Flash a zone on/off to help user identify it physically.

    Used during initial config flow when no coordinator is running.
    Creates a temporary client and tears it down immediately.
    Uses gentle 1-second fades so dimmers ramp smoothly.
    """
    from .pyradiora_classic.commands import set_dimmer_level

    fade_sec = 1
    cycle_time = fade_sec * 2  # one fade up + one fade down
    cycles = max(1, duration // cycle_time)

    client = RadioRAClient(url=url, bridged=(system != System.NONE))
    try:
        await client.connect()
        for _ in range(cycles):
            await client._send(set_dimmer_level(zone, 100, fade_sec=fade_sec, system=system))
            await asyncio.sleep(fade_sec)
            await client._send(set_dimmer_level(zone, 0, fade_sec=fade_sec, system=system))
            await asyncio.sleep(fade_sec)
        # Leave light on
        await client._send(set_dimmer_level(zone, 100, fade_sec=fade_sec, system=system))
    finally:
        await client.disconnect()


async def _flash_zone_via_coordinator(
    coordinator: "RadioRACoordinator", zone: int, system: System = System.NONE, duration: int = 5
) -> None:
    """Flash a zone using an already-running coordinator's client.

    Used during options flow when the coordinator is active.
    No extra connection — commands go through the existing queued pipeline.
    Uses gentle 1-second fades so dimmers ramp smoothly.
    """
    from .pyradiora_classic.commands import set_dimmer_level

    fade_sec = 1
    cycle_time = fade_sec * 2
    cycles = max(1, duration // cycle_time)

    for _ in range(cycles):
        await coordinator.async_send_raw(set_dimmer_level(zone, 100, fade_sec=fade_sec, system=system))
        await asyncio.sleep(fade_sec)
        await coordinator.async_send_raw(set_dimmer_level(zone, 0, fade_sec=fade_sec, system=system))
        await asyncio.sleep(fade_sec)
    # Leave light on
    await coordinator.async_send_raw(set_dimmer_level(zone, 100, fade_sec=fade_sec, system=system))


async def _discover_zones(url: str, bridged: bool) -> list[dict[str, Any]]:
    """Connect and query ZMPI to discover assigned zones."""
    client = RadioRAClient(url=url, bridged=bridged)
    try:
        await client.connect()
        zone_maps = await client.get_zone_map()
    finally:
        await client.disconnect()

    discovered: list[dict[str, Any]] = []
    for zm in zone_maps:
        for zone_num in range(1, 33):
            is_on = zm.is_zone_on(zone_num)
            if is_on is not None:
                discovered.append({
                    "zone": zone_num,
                    "is_on": is_on,
                    "system": zm.system.value if zm.system != System.NONE else None,
                })
    return discovered


class RadioRAClassicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RadioRA Classic."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._url: str = ""
        self._bridged: bool = False
        self._controller_id: str = ""
        self._discovered_zones: list[dict[str, Any]] = []
        self._selected_zones: list[int] = []
        self._zone_configs: list[dict[str, Any]] = []
        self._current_zone_index: int = 0
        self._auto_flash: bool = False
        self._flash_duration: int = 5

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RadioRAOptionsFlow:
        """Get the options flow handler."""
        return RadioRAOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step — connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input["name"]
            url = user_input["url"]
            bridged = user_input.get("bridged", False)
            controller_id = slugify(name)

            # Check URL uniqueness
            for entry in self._async_current_entries():
                if entry.data.get(CONF_URL) == url:
                    return self.async_abort(reason="already_configured")

            # Check controller_id uniqueness
            for entry in self._async_current_entries():
                if entry.options.get(CONF_CONTROLLER_ID) == controller_id:
                    errors["name"] = "duplicated_controller_id"
                    break

            if not errors:
                # Validate URL format
                if not _is_valid_url(url):
                    errors["url"] = "invalid_url"

            if not errors:
                # Test connection
                try:
                    await _try_connection(url, bridged)
                except (RadioRAConnectionError, RadioRATimeoutError, OSError):
                    errors["url"] = "connection_error"

            if not errors:
                self._url = url
                self._bridged = bridged
                self._controller_id = controller_id
                return await self.async_step_discover_zones()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("name"): TextSelector(),
                vol.Required("url"): TextSelector(),
                vol.Optional("bridged", default=False): BooleanSelector(),
            }),
            errors=errors,
        )

    async def async_step_discover_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Discover assigned zones via ZMPI."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected = user_input.get("selected_zones", [])
            if selected:
                self._selected_zones = [int(z) for z in selected]
                self._current_zone_index = 0
                self._zone_configs = []
                return await self.async_step_ask_identify()
            # No zones selected — create entry with empty zones
            return self._create_entry()

        # Discover zones
        try:
            self._discovered_zones = await _discover_zones(self._url, self._bridged)
        except (RadioRAConnectionError, RadioRATimeoutError, OSError):
            errors["base"] = "connection_error"
            return self.async_show_form(
                step_id="discover_zones",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        if not self._discovered_zones:
            errors["base"] = "no_zones_found"
            return self.async_show_form(
                step_id="discover_zones",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        # Build multi-select options
        options = {
            str(z["zone"]): f"Zone {z['zone']} — {'ON' if z['is_on'] else 'OFF'}"
            + (f" (S{z['system']})" if z.get("system") else "")
            for z in self._discovered_zones
        }

        return self.async_show_form(
            step_id="discover_zones",
            data_schema=vol.Schema({
                vol.Optional("selected_zones"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": k, "label": v} for k, v in options.items()
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    async def async_step_name_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Name and configure each selected zone sequentially."""
        if user_input is not None:
            zone_num = self._selected_zones[self._current_zone_index]
            system = self._get_zone_system(zone_num)

            config: dict[str, Any] = {
                "zone": zone_num,
                "name": user_input["name"],
                "mode": user_input.get("mode", "dimmer"),
                "area": user_input.get("area") or None,
                "fade_sec": int(user_input["fade_sec"]) if user_input.get("fade_sec") else None,
            }
            if system:
                config["system"] = system
            self._zone_configs.append(config)

            self._current_zone_index += 1
            if self._current_zone_index < len(self._selected_zones):
                return await self.async_step_name_zones()
            return self._create_entry()

        # Flash zone if user opted in
        zone_num = self._selected_zones[self._current_zone_index]
        if self._auto_flash:
            system = self._get_zone_system(zone_num)
            try:
                await _flash_zone(
                    self._url, zone_num,
                    System(int(system)) if system else System.NONE,
                    duration=self._flash_duration,
                )
            except (RadioRAConnectionError, RadioRATimeoutError, OSError, asyncio.TimeoutError):
                _LOGGER.debug("Auto-flash failed for zone %s", zone_num)

        return self.async_show_form(
            step_id="name_zones",
            data_schema=vol.Schema({
                vol.Required("name", default=f"Zone {zone_num}"): TextSelector(),
                vol.Optional("mode", default="dimmer"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "dimmer", "label": "Dimmer"},
                            {"value": "onoff", "label": "On/Off Only"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("area"): AreaSelector(),
                vol.Optional("fade_sec"): NumberSelector(
                    NumberSelectorConfig(min=0, max=240, mode=NumberSelectorMode.BOX)
                ),
            }),
            description_placeholders={"zone_number": str(zone_num)},
        )

    async def async_step_ask_identify(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask user if they want zones to auto-flash during setup."""
        if user_input is not None:
            self._auto_flash = user_input.get("auto_flash", False)
            self._flash_duration = int(user_input.get("flash_duration", 5))
            return await self.async_step_name_zones()

        return self.async_show_form(
            step_id="ask_identify",
            data_schema=vol.Schema({
                vol.Required("auto_flash", default=True): BooleanSelector(),
                vol.Required("flash_duration", default=5): NumberSelector(
                    NumberSelectorConfig(min=2, max=30, mode=NumberSelectorMode.BOX)
                ),
            }),
        )

    def _get_zone_system(self, zone_num: int) -> str | None:
        """Look up system string for a zone from discovery data."""
        for z in self._discovered_zones:
            if z["zone"] == zone_num:
                return z.get("system")
        return None

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration (change URL/bridged)."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input["url"]
            bridged = user_input.get("bridged", False)

            if not _is_valid_url(url):
                errors["url"] = "invalid_url"

            if not errors:
                try:
                    await _try_connection(url, bridged)
                except (RadioRAConnectionError, RadioRATimeoutError, OSError):
                    errors["url"] = "connection_error"

            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_URL: url, CONF_BRIDGED: bridged},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required("url", default=entry.data.get(CONF_URL, "")): TextSelector(),
                vol.Optional(
                    "bridged", default=entry.data.get(CONF_BRIDGED, False)
                ): BooleanSelector(),
            }),
            errors=errors,
        )

    def _create_entry(self) -> ConfigFlowResult:
        """Create the config entry."""
        return self.async_create_entry(
            title=self._controller_id,
            data={
                CONF_URL: self._url,
                CONF_BRIDGED: self._bridged,
            },
            options={
                CONF_CONTROLLER_ID: self._controller_id,
                CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                CONF_ZONES: self._zone_configs,
                CONF_PHANTOM_BUTTONS: [],
                CONF_MASTER_CONTROLS: [],
            },
        )


def _is_valid_url(url: str) -> bool:
    """Basic URL validation for supported schemes."""
    if url.startswith(("socket://", "tcp://", "rfc2217://")):
        return True
    if url.startswith("/dev/") or url.startswith("COM"):
        return True
    return False


def _parse_csv_content(content: str) -> tuple[list[dict], list[str]]:
    """Parse CSV, return (devices, errors). Atomic: all-or-nothing."""
    import csv
    from io import StringIO

    errors: list[str] = []
    devices: list[dict] = []

    reader = csv.DictReader(StringIO(content))
    for row_num, row in enumerate(reader, start=2):
        device_type = (row.get("type") or "").strip().lower()

        if device_type == "zone":
            zone = _parse_int(row.get("number"), 1, 32)
            if zone is None:
                errors.append(f"Row {row_num}: invalid zone number (must be 1-32)")
                continue
            name = (row.get("name") or "").strip()
            if not name:
                errors.append(f"Row {row_num}: missing required field 'name'")
                continue
            mode = (row.get("mode") or "dimmer").strip().lower()
            if mode not in ("dimmer", "onoff"):
                errors.append(f"Row {row_num}: mode must be 'dimmer' or 'onoff'")
                continue
            config: dict[str, Any] = {
                "zone": zone,
                "name": name,
                "mode": mode,
                "area": (row.get("area") or "").strip() or None,
                "fade_sec": _parse_int(row.get("fade_sec"), 0, 240),
            }
            system = _parse_int(row.get("system"), 1, 2)
            if system is not None:
                config["system"] = system
            devices.append({"type": "zone", **config})

        elif device_type == "phantom":
            button = _parse_int(row.get("number"), 1, 15)
            if button is None:
                errors.append(f"Row {row_num}: invalid button number (must be 1-15)")
                continue
            name = (row.get("name") or "").strip()
            if not name:
                errors.append(f"Row {row_num}: missing required field 'name'")
                continue
            devices.append({
                "type": "phantom",
                "button": button,
                "name": name,
                "area": (row.get("area") or "").strip() or None,
            })

        elif device_type == "master":
            number_str = (row.get("number") or "").strip()
            parts = number_str.split(":")
            if len(parts) != 2:
                errors.append(f"Row {row_num}: master format must be 'mc:button'")
                continue
            mc = _parse_int(parts[0], 1, 99)
            btn = _parse_int(parts[1], 1, 99)
            if mc is None or btn is None:
                errors.append(f"Row {row_num}: invalid master control numbers")
                continue
            name = (row.get("name") or "").strip()
            if not name:
                errors.append(f"Row {row_num}: missing required field 'name'")
                continue
            devices.append({
                "type": "master",
                "master_control": mc,
                "button": btn,
                "name": name,
                "area": (row.get("area") or "").strip() or None,
            })
        else:
            errors.append(
                f"Row {row_num}: unknown type '{device_type}' "
                f"(expected zone, phantom, or master)"
            )

    return devices, errors


def _parse_int(value: str | None, min_val: int, max_val: int) -> int | None:
    """Parse int within range, or None."""
    if not value:
        return None
    try:
        n = int(value)
    except (ValueError, TypeError):
        return None
    if n < min_val or n > max_val:
        return None
    return n


class RadioRAOptionsFlow(OptionsFlow):
    """Options flow for managing devices and settings."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        super().__init__()
        self._entry = config_entry
        self._edit_zone: int | None = None
        self._edit_phantom: int | None = None
        self._edit_master: tuple[int, int] | None = None
        self._discovered_new_zones: list[dict[str, Any]] = []
        self._auto_flash: bool = False
        self._flash_duration: int = 5

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the main options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "manage_zones",
                "manage_phantom_buttons",
                "manage_master_controls",
                "controller_settings",
                "import_csv",
                "export_csv",
                "rediscover_zones",
                "query_firmware_version",
            ],
        )

    # --- Zone Management ---

    async def async_step_manage_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Zone management sub-menu."""
        return self.async_show_menu(
            step_id="manage_zones",
            menu_options=["identify_add_zone", "add_zone", "select_edit_zone", "remove_zone"],
        )

    async def async_step_add_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a new zone."""
        errors: dict[str, str] = {}

        if user_input is not None:
            zone_num = int(user_input["zone"])
            existing = self._entry.options.get(CONF_ZONES, [])
            if any(z["zone"] == zone_num for z in existing):
                errors["zone"] = "duplicated_zone"
            else:
                config: dict[str, Any] = {
                    "zone": zone_num,
                    "name": user_input["name"],
                    "mode": user_input.get("mode", "dimmer"),
                    "area": user_input.get("area") or None,
                    "fade_sec": int(user_input["fade_sec"]) if user_input.get("fade_sec") else None,
                }
                system = user_input.get("system")
                if system:
                    config["system"] = int(system)
                new_zones = [*existing, config]
                return self._save_options({CONF_ZONES: new_zones})

        schema: dict[Any, Any] = {
            vol.Required("zone"): NumberSelector(
                NumberSelectorConfig(min=1, max=32, mode=NumberSelectorMode.BOX)
            ),
            vol.Required("name"): TextSelector(),
            vol.Optional("mode", default="dimmer"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "dimmer", "label": "Dimmer"},
                        {"value": "onoff", "label": "On/Off Only"},
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional("area"): AreaSelector(),
            vol.Optional("fade_sec"): NumberSelector(
                NumberSelectorConfig(min=0, max=240, mode=NumberSelectorMode.BOX)
            ),
        }
        if self._entry.data.get(CONF_BRIDGED):
            schema[vol.Optional("system")] = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "1", "label": "System 1"},
                        {"value": "2", "label": "System 2"},
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )

        # Show existing zones in description for context
        existing = self._entry.options.get(CONF_ZONES, [])
        existing_summary = "\n".join(
            f"Zone {z['zone']}: {z['name']} ✓"
            for z in sorted(existing, key=lambda x: x["zone"])
        )

        return self.async_show_form(
            step_id="add_zone",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={"configured_zones": existing_summary} if existing_summary else {},
        )

    async def async_step_identify_add_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Flash a zone by number to help identify it before adding."""
        if user_input is not None:
            zone_num = int(user_input["zone"]) if user_input.get("zone") else None
            if zone_num:
                system = user_input.get("system")
                duration = int(user_input.get("flash_duration", 5))
                try:
                    coordinator = self._entry.runtime_data.coordinator
                    await _flash_zone_via_coordinator(
                        coordinator, zone_num,
                        System(int(system)) if system else System.NONE,
                        duration=duration,
                    )
                except (RadioRAConnectionError, RadioRATimeoutError, OSError, asyncio.TimeoutError):
                    _LOGGER.debug("Flash identify failed for zone %s", zone_num)
            return await self.async_step_add_zone()

        schema: dict[Any, Any] = {
            vol.Required("zone"): NumberSelector(
                NumberSelectorConfig(min=1, max=32, mode=NumberSelectorMode.BOX)
            ),
            vol.Required("flash_duration", default=5): NumberSelector(
                NumberSelectorConfig(min=2, max=30, mode=NumberSelectorMode.BOX)
            ),
        }
        if self._entry.data.get(CONF_BRIDGED):
            schema[vol.Optional("system")] = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "1", "label": "System 1"},
                        {"value": "2", "label": "System 2"},
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )

        return self.async_show_form(
            step_id="identify_add_zone",
            data_schema=vol.Schema(schema),
        )

    async def async_step_select_edit_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a zone to edit."""
        zones = self._entry.options.get(CONF_ZONES, [])
        if not zones:
            return self.async_abort(reason="no_zones_found")

        if user_input is not None:
            self._edit_zone = int(user_input["zone"])
            return await self.async_step_edit_zone()

        options = [
            {"value": str(z["zone"]), "label": f"Zone {z['zone']}: {z['name']}"}
            for z in zones
        ]
        return self.async_show_form(
            step_id="select_edit_zone",
            data_schema=vol.Schema({
                vol.Required("zone"): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                ),
            }),
        )

    async def async_step_edit_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit an existing zone."""
        zones = self._entry.options.get(CONF_ZONES, [])
        current = next((z for z in zones if z["zone"] == self._edit_zone), None)
        if current is None:
            return self.async_abort(reason="no_zones_found")

        if user_input is not None:
            updated = {
                "zone": self._edit_zone,
                "name": user_input["name"],
                "mode": user_input.get("mode", "dimmer"),
                "area": user_input.get("area") or None,
                "fade_sec": int(user_input["fade_sec"]) if user_input.get("fade_sec") else None,
            }
            system = user_input.get("system")
            if system:
                updated["system"] = int(system)
            elif "system" in current:
                updated["system"] = current["system"]
            new_zones = [updated if z["zone"] == self._edit_zone else z for z in zones]
            return self._save_options({CONF_ZONES: new_zones})

        fade_default = current.get("fade_sec")
        fade_key = (
            vol.Optional("fade_sec", default=fade_default)
            if fade_default is not None
            else vol.Optional("fade_sec")
        )
        schema: dict[Any, Any] = {
            vol.Required("name", default=current["name"]): TextSelector(),
            vol.Optional("mode", default=current.get("mode", "dimmer")): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "dimmer", "label": "Dimmer"},
                        {"value": "onoff", "label": "On/Off Only"},
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional("area", default=current.get("area") or ""): AreaSelector(),
            fade_key: NumberSelector(
                NumberSelectorConfig(min=0, max=240, mode=NumberSelectorMode.BOX)
            ),
        }
        if self._entry.data.get(CONF_BRIDGED):
            schema[vol.Optional("system", default=str(current.get("system", "")))] = (
                SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "1", "label": "System 1"},
                            {"value": "2", "label": "System 2"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            )

        return self.async_show_form(step_id="edit_zone", data_schema=vol.Schema(schema))

    async def async_step_remove_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove zones."""
        zones = self._entry.options.get(CONF_ZONES, [])
        if not zones:
            return self.async_abort(reason="no_zones_found")

        if user_input is not None:
            to_remove = {int(z) for z in user_input.get("zones", [])}
            new_zones = [z for z in zones if z["zone"] not in to_remove]
            return self._save_options({CONF_ZONES: new_zones})

        options = [
            {"value": str(z["zone"]), "label": f"Zone {z['zone']}: {z['name']}"}
            for z in zones
        ]
        return self.async_show_form(
            step_id="remove_zone",
            data_schema=vol.Schema({
                vol.Required("zones"): SelectSelector(
                    SelectSelectorConfig(
                        options=options, multiple=True, mode=SelectSelectorMode.LIST
                    )
                ),
            }),
        )

    # --- Phantom Button Management ---

    async def async_step_manage_phantom_buttons(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Phantom button sub-menu."""
        return self.async_show_menu(
            step_id="manage_phantom_buttons",
            menu_options=["add_phantom", "select_edit_phantom", "remove_phantom"],
        )

    async def async_step_add_phantom(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a phantom button."""
        errors: dict[str, str] = {}

        if user_input is not None:
            btn = int(user_input["button"])
            existing = self._entry.options.get(CONF_PHANTOM_BUTTONS, [])
            if any(b["button"] == btn for b in existing):
                errors["button"] = "duplicated_button"
            else:
                config = {
                    "button": btn,
                    "name": user_input["name"],
                    "area": user_input.get("area") or None,
                }
                new_buttons = [*existing, config]
                return self._save_options({CONF_PHANTOM_BUTTONS: new_buttons})

        return self.async_show_form(
            step_id="add_phantom",
            data_schema=vol.Schema({
                vol.Required("button"): NumberSelector(
                    NumberSelectorConfig(min=1, max=15, mode=NumberSelectorMode.BOX)
                ),
                vol.Required("name"): TextSelector(),
                vol.Optional("area"): AreaSelector(),
            }),
            errors=errors,
        )

    async def async_step_select_edit_phantom(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select phantom button to edit."""
        buttons = self._entry.options.get(CONF_PHANTOM_BUTTONS, [])
        if not buttons:
            return self.async_abort(reason="no_zones_found")

        if user_input is not None:
            self._edit_phantom = int(user_input["button"])
            return await self.async_step_edit_phantom()

        options = [
            {"value": str(b["button"]), "label": f"Button {b['button']}: {b['name']}"}
            for b in buttons
        ]
        return self.async_show_form(
            step_id="select_edit_phantom",
            data_schema=vol.Schema({
                vol.Required("button"): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                ),
            }),
        )

    async def async_step_edit_phantom(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit a phantom button."""
        buttons = self._entry.options.get(CONF_PHANTOM_BUTTONS, [])
        current = next((b for b in buttons if b["button"] == self._edit_phantom), None)
        if current is None:
            return self.async_abort(reason="no_zones_found")

        if user_input is not None:
            updated = {
                "button": self._edit_phantom,
                "name": user_input["name"],
                "area": user_input.get("area") or None,
            }
            new_buttons = [
                updated if b["button"] == self._edit_phantom else b for b in buttons
            ]
            return self._save_options({CONF_PHANTOM_BUTTONS: new_buttons})

        return self.async_show_form(
            step_id="edit_phantom",
            data_schema=vol.Schema({
                vol.Required("name", default=current["name"]): TextSelector(),
                vol.Optional("area", default=current.get("area") or ""): AreaSelector(),
            }),
        )

    async def async_step_remove_phantom(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove phantom buttons."""
        buttons = self._entry.options.get(CONF_PHANTOM_BUTTONS, [])
        if not buttons:
            return self.async_abort(reason="no_zones_found")

        if user_input is not None:
            to_remove = {int(b) for b in user_input.get("buttons", [])}
            new_buttons = [b for b in buttons if b["button"] not in to_remove]
            return self._save_options({CONF_PHANTOM_BUTTONS: new_buttons})

        options = [
            {"value": str(b["button"]), "label": f"Button {b['button']}: {b['name']}"}
            for b in buttons
        ]
        return self.async_show_form(
            step_id="remove_phantom",
            data_schema=vol.Schema({
                vol.Required("buttons"): SelectSelector(
                    SelectSelectorConfig(
                        options=options, multiple=True, mode=SelectSelectorMode.LIST
                    )
                ),
            }),
        )

    # --- Master Control Management ---

    async def async_step_manage_master_controls(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Master control sub-menu."""
        return self.async_show_menu(
            step_id="manage_master_controls",
            menu_options=["add_master", "select_edit_master", "remove_master"],
        )

    async def async_step_add_master(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a master control button."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mc = int(user_input["master_control"])
            btn = int(user_input["button"])
            existing = self._entry.options.get(CONF_MASTER_CONTROLS, [])
            if any(
                m["master_control"] == mc and m["button"] == btn for m in existing
            ):
                errors["master_control"] = "duplicated_master"
            else:
                config = {
                    "master_control": mc,
                    "button": btn,
                    "name": user_input["name"],
                    "area": user_input.get("area") or None,
                }
                new_masters = [*existing, config]
                return self._save_options({CONF_MASTER_CONTROLS: new_masters})

        return self.async_show_form(
            step_id="add_master",
            data_schema=vol.Schema({
                vol.Required("master_control"): NumberSelector(
                    NumberSelectorConfig(min=1, max=99, mode=NumberSelectorMode.BOX)
                ),
                vol.Required("button"): NumberSelector(
                    NumberSelectorConfig(min=1, max=99, mode=NumberSelectorMode.BOX)
                ),
                vol.Required("name"): TextSelector(),
                vol.Optional("area"): AreaSelector(),
            }),
            errors=errors,
        )

    async def async_step_select_edit_master(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select master control to edit."""
        masters = self._entry.options.get(CONF_MASTER_CONTROLS, [])
        if not masters:
            return self.async_abort(reason="no_zones_found")

        if user_input is not None:
            parts = user_input["master"].split(":")
            self._edit_master = (int(parts[0]), int(parts[1]))
            return await self.async_step_edit_master()

        options = [
            {
                "value": f"{m['master_control']}:{m['button']}",
                "label": f"MC{m['master_control']}:B{m['button']} — {m['name']}",
            }
            for m in masters
        ]
        return self.async_show_form(
            step_id="select_edit_master",
            data_schema=vol.Schema({
                vol.Required("master"): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                ),
            }),
        )

    async def async_step_edit_master(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit a master control."""
        masters = self._entry.options.get(CONF_MASTER_CONTROLS, [])
        mc_num, btn_num = self._edit_master  # type: ignore[misc]
        current = next(
            (m for m in masters if m["master_control"] == mc_num and m["button"] == btn_num),
            None,
        )
        if current is None:
            return self.async_abort(reason="no_zones_found")

        if user_input is not None:
            updated = {
                "master_control": mc_num,
                "button": btn_num,
                "name": user_input["name"],
                "area": user_input.get("area") or None,
            }
            new_masters = [
                updated
                if m["master_control"] == mc_num and m["button"] == btn_num
                else m
                for m in masters
            ]
            return self._save_options({CONF_MASTER_CONTROLS: new_masters})

        return self.async_show_form(
            step_id="edit_master",
            data_schema=vol.Schema({
                vol.Required("name", default=current["name"]): TextSelector(),
                vol.Optional("area", default=current.get("area") or ""): AreaSelector(),
            }),
        )

    async def async_step_remove_master(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove master controls."""
        masters = self._entry.options.get(CONF_MASTER_CONTROLS, [])
        if not masters:
            return self.async_abort(reason="no_zones_found")

        if user_input is not None:
            to_remove = set(user_input.get("masters", []))
            new_masters = [
                m for m in masters
                if f"{m['master_control']}:{m['button']}" not in to_remove
            ]
            return self._save_options({CONF_MASTER_CONTROLS: new_masters})

        options = [
            {
                "value": f"{m['master_control']}:{m['button']}",
                "label": f"MC{m['master_control']}:B{m['button']} — {m['name']}",
            }
            for m in masters
        ]
        return self.async_show_form(
            step_id="remove_master",
            data_schema=vol.Schema({
                vol.Required("masters"): SelectSelector(
                    SelectSelectorConfig(
                        options=options, multiple=True, mode=SelectSelectorMode.LIST
                    )
                ),
            }),
        )

    # --- Settings ---

    async def async_step_controller_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit controller settings."""
        if user_input is not None:
            return self._save_options({
                CONF_POLL_INTERVAL: int(user_input["poll_interval"]),
                CONF_DEBUG_LOGGING: bool(
                    user_input.get(CONF_DEBUG_LOGGING, DEFAULT_DEBUG_LOGGING)
                ),
            })

        current_interval = self._entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        current_debug = self._entry.options.get(
            CONF_DEBUG_LOGGING, DEFAULT_DEBUG_LOGGING
        )
        return self.async_show_form(
            step_id="controller_settings",
            data_schema=vol.Schema({
                vol.Required("poll_interval", default=current_interval): NumberSelector(
                    NumberSelectorConfig(min=0, max=86400, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_DEBUG_LOGGING, default=current_debug
                ): BooleanSelector(),
            }),
        )

    # --- CSV Import/Export ---

    async def async_step_import_csv(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Import devices from CSV."""
        errors: dict[str, str] = {}

        if user_input is not None:
            content = user_input.get("csv_content", "")
            if len(content) > MAX_CSV_SIZE:
                errors["csv_content"] = "csv_too_large"
            else:
                devices, parse_errors = _parse_csv_content(content)
                if parse_errors:
                    error_text = "\n".join(parse_errors[:20])
                    errors["csv_content"] = "csv_validation_failed"
                    return self.async_show_form(
                        step_id="import_csv",
                        data_schema=vol.Schema({
                            vol.Required("csv_content"): TextSelector(
                                TextSelectorConfig(multiline=True)
                            ),
                        }),
                        errors=errors,
                        description_placeholders={"error_details": error_text},
                    )
                if not devices:
                    errors["csv_content"] = "no_devices_in_csv"
                else:
                    return self._apply_csv_import(devices)

        return self.async_show_form(
            step_id="import_csv",
            data_schema=vol.Schema({
                vol.Required("csv_content"): TextSelector(
                    TextSelectorConfig(multiline=True)
                ),
            }),
            errors=errors,
        )

    async def async_step_export_csv(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show CSV export in a text area."""
        from . import _build_csv_export

        if user_input is not None:
            return await self.async_step_init()

        csv_content = _build_csv_export(self._entry.options)
        return self.async_show_form(
            step_id="export_csv",
            data_schema=vol.Schema({
                vol.Optional("csv_export", default=csv_content): TextSelector(
                    TextSelectorConfig(multiline=True)
                ),
            }),
        )

    # --- Re-discover ---

    async def async_step_rediscover_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-discover zones from hardware."""
        errors: dict[str, str] = {}
        url = self._entry.data[CONF_URL]
        bridged = self._entry.data.get(CONF_BRIDGED, False)

        try:
            discovered = await _discover_zones(url, bridged)
        except (RadioRAConnectionError, RadioRATimeoutError, OSError):
            errors["base"] = "connection_error"
            return self.async_show_form(
                step_id="rediscover_zones",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        # Build zone list with existing names annotated
        existing_zones = {z["zone"]: z for z in self._entry.options.get(CONF_ZONES, [])}
        all_discovered = discovered
        new_zones = [z for z in discovered if z["zone"] not in existing_zones]

        if not new_zones:
            errors["base"] = "no_zones_found"
            return self.async_show_form(
                step_id="rediscover_zones",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        # Pass both new zones and existing lookup to results step
        return await self.async_step_rediscover_results(
            new_zones=new_zones, existing_zones=existing_zones
        )

    async def async_step_rediscover_results(
        self,
        user_input: dict[str, Any] | None = None,
        new_zones: list[dict[str, Any]] | None = None,
        existing_zones: dict[int, dict[str, Any]] | None = None,
    ) -> ConfigFlowResult:
        """Show discovered zones for selection, annotating already-configured ones."""
        if new_zones is not None:
            self._discovered_new_zones = new_zones
        if existing_zones is not None:
            self._existing_zones_lookup = existing_zones

        if user_input is not None:
            selected = [int(z) for z in user_input.get("selected_zones", [])]
            if selected:
                # Store selections, proceed to ask about identify then naming flow
                self._rediscover_selected = selected
                self._rediscover_zone_configs: list[dict[str, Any]] = []
                self._rediscover_zone_index = 0
                return await self.async_step_ask_identify_rediscover()
            return await self.async_step_init()

        # Build labels — new zones available for selection
        existing_lookup = getattr(self, "_existing_zones_lookup", {})
        options = []
        for z in self._discovered_new_zones:
            label = f"Zone {z['zone']} — {'ON' if z['is_on'] else 'OFF'}"
            if z.get("system"):
                label += f" (S{z['system']})"
            options.append({"value": str(z["zone"]), "label": label})

        # Build description showing already-configured zones for context
        configured_lines = []
        for zone_num, zone_cfg in sorted(existing_lookup.items()):
            state_hint = "configured"
            configured_lines.append(f"Zone {zone_num}: {zone_cfg['name']} ✓")

        description_text = ""
        if configured_lines:
            description_text = (
                "Already configured:\n" + "\n".join(configured_lines)
                + "\n\nSelect new zones to add:"
            )

        return self.async_show_form(
            step_id="rediscover_results",
            data_schema=vol.Schema({
                vol.Optional("selected_zones"): SelectSelector(
                    SelectSelectorConfig(
                        options=options, multiple=True, mode=SelectSelectorMode.LIST
                    )
                ),
            }),
            description_placeholders={"existing_zones": description_text} if description_text else {},
        )

    async def async_step_ask_identify_rediscover(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask user if they want zones to auto-flash during rediscovery setup."""
        if user_input is not None:
            self._auto_flash = user_input.get("auto_flash", False)
            self._flash_duration = int(user_input.get("flash_duration", 5))
            return await self.async_step_name_rediscovered_zone()

        return self.async_show_form(
            step_id="ask_identify_rediscover",
            data_schema=vol.Schema({
                vol.Required("auto_flash", default=True): BooleanSelector(),
                vol.Required("flash_duration", default=5): NumberSelector(
                    NumberSelectorConfig(min=2, max=30, mode=NumberSelectorMode.BOX)
                ),
            }),
        )

    async def async_step_name_rediscovered_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Name and configure each rediscovered zone sequentially."""
        if user_input is not None:
            zone_num = self._rediscover_selected[self._rediscover_zone_index]
            system = self._get_rediscover_zone_system(zone_num)

            config: dict[str, Any] = {
                "zone": zone_num,
                "name": user_input["name"],
                "mode": user_input.get("mode", "dimmer"),
                "area": user_input.get("area") or None,
                "fade_sec": int(user_input["fade_sec"]) if user_input.get("fade_sec") else None,
            }
            if system:
                config["system"] = system
            self._rediscover_zone_configs.append(config)

            self._rediscover_zone_index += 1
            if self._rediscover_zone_index < len(self._rediscover_selected):
                return await self.async_step_name_rediscovered_zone()

            # All zones named — save them
            existing = list(self._entry.options.get(CONF_ZONES, []))
            existing.extend(self._rediscover_zone_configs)
            return self._save_options({CONF_ZONES: existing})

        zone_num = self._rediscover_selected[self._rediscover_zone_index]

        # Flash zone if user opted in
        if self._auto_flash:
            system = self._get_rediscover_zone_system(zone_num)
            try:
                coordinator = self._entry.runtime_data.coordinator
                await _flash_zone_via_coordinator(
                    coordinator, zone_num,
                    System(int(system)) if system else System.NONE,
                    duration=self._flash_duration,
                )
            except (RadioRAConnectionError, RadioRATimeoutError, OSError, asyncio.TimeoutError):
                _LOGGER.debug("Auto-flash failed for zone %s", zone_num)

        schema: dict[Any, Any] = {
            vol.Required("name", default=f"Zone {zone_num}"): TextSelector(),
            vol.Optional("mode", default="dimmer"): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "dimmer", "label": "Dimmer"},
                        {"value": "onoff", "label": "On/Off Only"},
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional("area"): AreaSelector(),
            vol.Optional("fade_sec"): NumberSelector(
                NumberSelectorConfig(min=0, max=240, mode=NumberSelectorMode.BOX)
            ),
        }
        if self._entry.data.get(CONF_BRIDGED):
            schema[vol.Optional("system")] = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "1", "label": "System 1"},
                        {"value": "2", "label": "System 2"},
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )

        return self.async_show_form(
            step_id="name_rediscovered_zone",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "zone_number": str(zone_num),
                "current": str(self._rediscover_zone_index + 1),
                "total": str(len(self._rediscover_selected)),
            },
        )

    def _get_rediscover_zone_system(self, zone_num: int) -> str | None:
        """Look up system string for a zone from rediscovery data."""
        for z in self._discovered_new_zones:
            if z["zone"] == zone_num:
                return z.get("system")
        return None

    # --- Firmware Version Query ---

    async def async_step_query_firmware_version(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Query and display hardware firmware version."""
        if user_input is not None:
            return await self.async_step_init()

        url = self._entry.data[CONF_URL]
        bridged = self._entry.data.get(CONF_BRIDGED, False)
        version_str = "Unknown"

        try:
            client = RadioRAClient(url=url, bridged=bridged)
            await client.connect()
            version_info = await client.get_version()
            version_str = f"{version_info.master_version} / {version_info.slave_version}"
            await client.disconnect()
        except (RadioRAConnectionError, RadioRATimeoutError, OSError):
            version_str = "Error: could not query device"

        return self.async_show_form(
            step_id="query_firmware_version",
            data_schema=vol.Schema({}),
            description_placeholders={"firmware_version": version_str},
        )

    # --- Helpers ---

    def _save_options(self, updates: dict[str, Any]) -> ConfigFlowResult:
        """Merge updates into options and create entry."""
        new_options = dict(self._entry.options)
        new_options.update(updates)
        return self.async_create_entry(data=new_options)

    def _apply_csv_import(self, devices: list[dict]) -> ConfigFlowResult:
        """Apply parsed CSV devices to options (merge/update)."""
        zones = list(self._entry.options.get(CONF_ZONES, []))
        phantoms = list(self._entry.options.get(CONF_PHANTOM_BUTTONS, []))
        masters = list(self._entry.options.get(CONF_MASTER_CONTROLS, []))

        for dev in devices:
            if dev["type"] == "zone":
                zone_data = {k: v for k, v in dev.items() if k != "type"}
                existing_idx = next(
                    (i for i, z in enumerate(zones) if z["zone"] == dev["zone"]), None
                )
                if existing_idx is not None:
                    zones[existing_idx] = zone_data
                else:
                    zones.append(zone_data)

            elif dev["type"] == "phantom":
                btn_data = {k: v for k, v in dev.items() if k != "type"}
                existing_idx = next(
                    (i for i, b in enumerate(phantoms) if b["button"] == dev["button"]),
                    None,
                )
                if existing_idx is not None:
                    phantoms[existing_idx] = btn_data
                else:
                    phantoms.append(btn_data)

            elif dev["type"] == "master":
                mc_data = {k: v for k, v in dev.items() if k != "type"}
                existing_idx = next(
                    (
                        i
                        for i, m in enumerate(masters)
                        if m["master_control"] == dev["master_control"]
                        and m["button"] == dev["button"]
                    ),
                    None,
                )
                if existing_idx is not None:
                    masters[existing_idx] = mc_data
                else:
                    masters.append(mc_data)

        return self._save_options({
            CONF_ZONES: zones,
            CONF_PHANTOM_BUTTONS: phantoms,
            CONF_MASTER_CONTROLS: masters,
        })
