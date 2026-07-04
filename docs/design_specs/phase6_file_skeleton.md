# Phase 6: File Tree & Module Skeleton

## Complete File Tree

```
custom_components/radiora_classic/
├── __init__.py              # Entry setup/unload, service registration, runtime_data
├── config_flow.py           # ConfigFlow (connection + discovery) + SchemaOptionsFlowHandler
├── coordinator.py           # RadioRACoordinator (DataUpdateCoordinator subclass)
├── client.py                # RadioRAClientWrapper (thin adapter over library)
├── light.py                 # RadioRALight entity (zones, dimmer + onoff)
├── switch.py                # RadioRAPhantomSwitch entity (phantom buttons 1-15)
├── button.py                # RadioRASystemButton entity (ALL ON/OFF)
├── event.py                 # RadioRAMasterEvent entity (master control presses)
├── sensor.py                # RadioRAConnectionSensor entity (diagnostic)
├── diagnostics.py           # Config entry diagnostics dump
├── const.py                 # Domain, config keys, defaults
├── models.py                # Dataclasses, type aliases, helpers
├── manifest.json            # HACS/HA metadata
├── strings.json             # UI strings (config flow, services, errors)
├── services.yaml            # Service definitions
├── icons.json               # MDI icon overrides (optional)
├── translations/
│   └── en.json              # English translations
└── pyradiora_classic/       # BUNDLED LIBRARY (verbatim from C:\repos\pyradiora_classic\src\)
    ├── __init__.py
    ├── client.py
    ├── client_sync.py
    ├── commands.py
    ├── const.py
    ├── exceptions.py
    ├── messages.py
    ├── protocol.py
    ├── transport.py
    ├── transport_sync.py
    └── py.typed
```

## Root-Level Repo Files

```
radiora_classic_ha/          # GitHub repo root
├── custom_components/
│   └── radiora_classic/     # (above)
├── tests/                   # Phase 7
├── hacs.json                # HACS repo metadata
├── README.md
├── LICENSE
├── pyproject.toml           # Dev deps (pytest, ruff, mypy)
└── .github/
    └── workflows/
        └── validate.yml     # CI: ruff + mypy + pytest
```

### Bundled Library Handling

The `pyradiora_classic/` directory lives **inside** `custom_components/radiora_classic/` as a sub-package. This is the same pattern HWI_HA uses with `hwi_protocol/`.

**Import path:** Only `client.py` instantiates `RadioRAClient`. Other files may import type definitions (enums, message dataclasses, constants) directly:
```python
# In custom_components/radiora_classic/client.py — instantiates the client
from .pyradiora_classic import RadioRAClient, RadioRAConnectionError, ...

# In coordinator.py, entity files — type imports only (no client instantiation)
from .pyradiora_classic import System, ButtonState, LocalZoneChange, ...
```

**Why this works:** HA loads custom components as Python packages. The directory `custom_components/radiora_classic/` is the package root. Any sub-directory with `__init__.py` is importable as a relative sub-package.

**`manifest.json` requirements:** Lists only the library's external deps (`pyserial`, `pyserial-asyncio-fast`) — NOT the library itself (it's bundled, not installed from PyPI).

**Future PyPI migration:** When `pyradiora-classic` is published:
1. Delete `custom_components/radiora_classic/pyradiora_classic/` directory
2. Add `"pyradiora-classic>=1.0.0"` to `manifest.json` requirements
3. Change `client.py` import from `from .pyradiora_classic import ...` to `from pyradiora_classic import ...`

---

## Module Responsibilities (1 sentence each)

| Module | Single Responsibility |
|--------|----------------------|
| `__init__.py` | Config entry lifecycle (setup/unload), service registration, `RadioRAData` runtime container |
| `config_flow.py` | All UI flows: initial connection + discovery, options CRUD, CSV import, reconfigure |
| `coordinator.py` | Owns client, manages push+poll hybrid, maintains state caches, provides entity API |
| `client.py` | Wraps `pyradiora_classic.RadioRAClient`; only file that instantiates the client |
| `light.py` | Zone light entities — brightness or on/off based on mode config |
| `switch.py` | Phantom button switch entities (1-15) with LED state feedback |
| `button.py` | System buttons (ALL ON=16, ALL OFF=17) — stateless press |
| `event.py` | Master control button press events — fires `press` event on MBP |
| `sensor.py` | Connection health diagnostic sensor |
| `diagnostics.py` | Redacted state dump for debugging |
| `const.py` | Domain name, config keys, default values — no logic |
| `models.py` | `RadioRAData` dataclass, type alias `RadioRAConfigEntry`, helper functions |

---

## Key Type Definitions (`models.py`)

```python
from dataclasses import dataclass
from homeassistant.config_entries import ConfigEntry
from .coordinator import RadioRACoordinator

@dataclass(slots=True)
class RadioRAData:
    """Runtime data stored in entry.runtime_data."""
    coordinator: RadioRACoordinator
    controller_id: str

type RadioRAConfigEntry = ConfigEntry[RadioRAData]
```

---

## `const.py`

```python
from typing import Final

DOMAIN: Final = "radiora_classic"

# Config keys
CONF_CONTROLLER_ID: Final = "controller_id"
CONF_URL: Final = "url"
CONF_BRIDGED: Final = "bridged"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_ZONES: Final = "zones"
CONF_PHANTOM_BUTTONS: Final = "phantom_buttons"
CONF_MASTER_CONTROLS: Final = "master_controls"
CONF_ZONE_NUMBER: Final = "zone"
CONF_MODE: Final = "mode"
CONF_FADE_SEC: Final = "fade_sec"
CONF_SYSTEM: Final = "system"
CONF_BUTTON_NUMBER: Final = "button"
CONF_MASTER_CONTROL: Final = "master_control"

# Defaults
DEFAULT_POLL_INTERVAL: Final = 30
DEFAULT_ZONE_MODE: Final = "dimmer"

# CSV limits
MAX_CSV_SIZE: Final = 500_000  # 500KB
MAX_CSV_ROWS: Final = 256
```

---

## `manifest.json`

```json
{
  "domain": "radiora_classic",
  "name": "Lutron RadioRA Classic",
  "codeowners": ["@numericOverflow"],
  "config_flow": true,
  "documentation": "https://github.com/numericOverflow/lutron_radiora_classic_ha",
  "integration_type": "hub",
  "iot_class": "local_push",
  "issue_tracker": "https://github.com/numericOverflow/lutron_radiora_classic_ha/issues",
  "loggers": ["custom_components.radiora_classic"],
  "requirements": ["pyserial>=3.5", "pyserial-asyncio-fast>=0.11"],
  "version": "1.0.0"
}
```

---

## `hacs.json`

```json
{
  "name": "Lutron RadioRA Classic",
  "render_readme": true,
  "homeassistant": "2025.1.0",
  "content_in_root": false
}
```

---

## `__init__.py` Skeleton

```python
"""Lutron RadioRA Classic integration."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv

from .const import CONF_CONTROLLER_ID, CONF_POLL_INTERVAL, CONF_URL, CONF_BRIDGED, DOMAIN
from .coordinator import RadioRACoordinator
from .models import RadioRAConfigEntry, RadioRAData

# Reject YAML configuration — config entry only
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.SENSOR,
]

async def async_setup_entry(hass: HomeAssistant, entry: RadioRAConfigEntry) -> bool:
    url = entry.data[CONF_URL]
    bridged = entry.data.get(CONF_BRIDGED, False)
    controller_id = entry.options[CONF_CONTROLLER_ID]
    poll_interval = entry.options.get(CONF_POLL_INTERVAL, 30)

    coordinator = RadioRACoordinator(hass, entry, url, bridged, controller_id, poll_interval)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = RadioRAData(coordinator=coordinator, controller_id=controller_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _shutdown(event):
        await coordinator.async_shutdown()
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: RadioRAConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.coordinator.async_shutdown()
    return True
```

### HA 2026 + HACS Compliance Checklist

| Requirement | Status | Notes |
|-------------|--------|-------|
| `manifest.json` has `config_flow: true` | ✓ | Required for UI setup |
| `manifest.json` has `version` field | ✓ | Required by HACS |
| `manifest.json` has `integration_type` | ✓ | `hub` — correct for multi-device controller |
| `hacs.json` present at repo root | ✓ | `content_in_root: false` → expects `custom_components/` dir |
| `hacs.json` has `homeassistant` minimum version | ✓ | Set to `2025.1.0` |
| `runtime_data` typed (not `hass.data[DOMAIN]`) | ✓ | Uses `ConfigEntry[RadioRAData]` pattern |
| `config_entry` param on coordinator | ✓ | Passed to `super().__init__()` |
| Platforms use `async_forward_entry_setups` (not `async_setup_platforms`) | ✓ | Current API |
| Unload uses `async_unload_platforms` | ✓ | Returns bool |
| No `async_setup_platform` (deprecated YAML) | ✓ | Config-entry only |
| `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)` | ✓ | Added to `__init__.py` skeleton above |
| Entity uses `AddConfigEntryEntitiesCallback` | ✓ | Type hint specified for all platform `async_setup_entry` signatures (Phase 4) |
| No `hass.data` usage | ✓ | All state in `entry.runtime_data` |
| `async_on_unload` for cleanup | ✓ | HA_STOP listener registered |
| Diagnostics returns redacted data | ✓ | Phase 5 |
| `strings.json` + `translations/en.json` present | ⚠️ Need to create | Required for config flow UI |
| Brand registration (optional for HACS) | — | Not required, but can submit to `home-assistant/brands` repo later |

**Items to add to `__init__.py`:**
```python
import homeassistant.helpers.config_validation as cv
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
```

**Entity platform signature (HA 2026):**
```python
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

async def async_setup_entry(
    hass: HomeAssistant,
    entry: RadioRAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None: ...
```

Both are minor — the overall design is compliant.
