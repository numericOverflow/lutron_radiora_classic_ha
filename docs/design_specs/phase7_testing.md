# Phase 7: Testing Harness & Validation Tests

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures (mock client, coordinator, entries)
├── test_config_flow.py      # Config flow + options flow tests
├── test_coordinator.py      # Push/poll state management tests
├── test_client.py           # Client wrapper tests
├── test_light.py            # Light entity behavior
├── test_switch.py           # Phantom button switch behavior
├── test_button.py           # ALL ON/OFF button behavior
├── test_event.py            # Master control event entity
├── test_sensor.py           # Connection health sensor
├── test_diagnostics.py      # Diagnostics output
├── test_csv.py              # CSV import/export parsing
└── test_init.py             # Entry setup/unload lifecycle
```

---

## `conftest.py` — Core Fixtures

```python
"""Shared test fixtures for RadioRA Classic integration tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from custom_components.radiora_classic.const import DOMAIN
from custom_components.radiora_classic.pyradiora_classic import (
    ZoneMap, LEDMap, LocalZoneChange, MasterButtonPress, VersionInfo,
    System, ZoneState, ButtonState,
)


@pytest.fixture
def mock_radiora_client():
    """Mock RadioRAClient that never touches hardware."""
    with patch(
        "custom_components.radiora_classic.client.RadioRAClient"
    ) as mock_cls:
        client = mock_cls.return_value
        client.connect = AsyncMock()
        client.start = AsyncMock()
        client.stop = AsyncMock()
        client.disconnect = AsyncMock()
        client.connected = True
        client.connected_at = None
        client.last_message_at = None
        client.reconnect_count = 0

        # Default zone map: zones 1-5 assigned, rest unassigned
        zone_map = ZoneMap(
            raw="ZMP,11001XXXXXXXXXXXXXXXXXXXXXXXXXXX",
            timestamp=...,
            states="11001" + "X" * 27,
            system=System.NONE,
        )
        client.get_zone_map = AsyncMock(return_value=[zone_map])

        # Default LED map: button 1 active, rest off
        led_map = LEDMap(
            raw="LMP,100000000000000",
            timestamp=...,
            bitmap="100000000000000",
        )
        client.get_led_map = AsyncMock(return_value=led_map)

        # Version
        client.get_version = AsyncMock(return_value=VersionInfo(
            raw="REV,1.0,1.0", timestamp=..., master_version="1.0", slave_version="1.0"
        ))

        # Commands are fire-and-forget
        client.set_dimmer_level = AsyncMock()
        client.switch_on = AsyncMock()
        client.switch_off = AsyncMock()
        client.button_press = AsyncMock()

        # State cache
        client.zone_states = {(System.NONE, 1): True, (System.NONE, 2): True}
        client.phantom_led_states = {1: True}

        yield client


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry with typical options."""
    return ConfigEntry(
        version=1,
        domain=DOMAIN,
        title="Main Floor",
        data={"url": "socket://192.168.1.50:4999", "bridged": False},
        options={
            "controller_id": "main_floor",
            "poll_interval": 30,
            "zones": [
                {"zone": 1, "name": "Living Room", "mode": "dimmer", "area": "Living Room", "fade_sec": None},
                {"zone": 2, "name": "Kitchen", "mode": "dimmer", "area": "Kitchen", "fade_sec": 3},
                {"zone": 5, "name": "Porch", "mode": "onoff", "area": "Exterior", "fade_sec": None},
            ],
            "phantom_buttons": [
                {"button": 1, "name": "Evening Scene", "area": "Living Room"},
            ],
            "master_controls": [
                {"master_control": 1, "button": 3, "name": "Kitchen Top", "area": "Kitchen"},
            ],
        },
    )
```

---

## Test Categories

### 1. Config Flow Tests (`test_config_flow.py`)

| Test | Validates |
|------|-----------|
| `test_user_step_success` | Connection validates, entry created with correct data/options split |
| `test_user_step_connection_failure` | Shows error, doesn't create entry |
| `test_user_step_duplicate_url` | Aborts with `already_configured` |
| `test_user_step_duplicate_controller_id` | Shows `duplicated_controller_id` error |
| `test_discover_zones` | ZMPI response parsed, multi-select shows assigned zones |
| `test_reconfigure_updates_url` | URL changes in entry.data, triggers reload |
| `test_options_add_zone` | Zone added to options, entry reloaded |
| `test_options_remove_zone` | Zone removed, entity cleaned from registry |
| `test_csv_import_valid` | All rows parsed, options updated |
| `test_csv_import_errors` | Atomic rejection, all row errors reported |

### 2. Coordinator Tests (`test_coordinator.py`)

| Test | Validates |
|------|-----------|
| `test_first_refresh_connects` | Lazy connect on first poll |
| `test_poll_updates_zone_states` | ZMP response updates `_zone_levels` cache |
| `test_poll_updates_phantom_states` | LMP response updates `_phantom_states` cache |
| `test_push_lzc_on` | LZC ON message sets zone level to 100 |
| `test_push_lzc_off` | LZC OFF message sets zone level to 0 |
| `test_push_mbp` | MBP message updates `_master_events` timestamp |
| `test_optimistic_dimmer` | `async_set_dimmer` updates cache before sending command |
| `test_optimistic_switch` | `async_switch_zone` updates cache before sending command |
| `test_reconnect_on_lost` | Next poll reconnects after connection loss |

### 3. Light Entity Tests (`test_light.py`)

| Test | Validates |
|------|-----------|
| `test_dimmer_brightness` | `brightness` property converts 0-100 → 0-255 |
| `test_dimmer_turn_on_with_brightness` | Sends SDL with correct level |
| `test_dimmer_turn_on_no_brightness` | Restores `_prev_level` (last non-zero brightness, not always 100%) |
| `test_dimmer_turn_off` | Sends SDL,zone,0 |
| `test_dimmer_turn_on_with_transition` | Sends SFA with `fade_sec` from kwargs |
| `test_dimmer_fade_from_config` | Uses zone config `fade_sec` when no transition kwarg |
| `test_dimmer_no_fade_default` | Omits fade when neither config nor kwarg set |
| `test_onoff_turn_on` | Sends SSL,zone,ON (no brightness) |
| `test_onoff_turn_off` | Sends SSL,zone,OFF |
| `test_onoff_no_brightness_slider` | `supported_color_modes` is `{ONOFF}` |
| `test_unique_id_format` | Matches `radiora_classic.{controller_id}.light.z{n}` |
| `test_device_info` | DeviceInfo has correct identifiers, name, suggested_area |

### 4. Switch Entity Tests (`test_switch.py`)

| Test | Validates |
|------|-----------|
| `test_phantom_is_on` | Reads from coordinator phantom cache |
| `test_phantom_turn_on` | Sends BP,button,ON |
| `test_phantom_turn_off` | Sends BP,button,OFF |

### 5. Button Entity Tests (`test_button.py`)

| Test | Validates |
|------|-----------|
| `test_all_on_press` | Sends BP,16,ON |
| `test_all_off_press` | Sends BP,17,OFF |

### 6. CSV Tests (`test_csv.py`)

| Test | Validates |
|------|-----------|
| `test_parse_valid_zones` | Correct zone dicts returned |
| `test_parse_valid_phantom` | Correct phantom dicts returned |
| `test_parse_valid_master` | Correct master format `mc:btn` parsed |
| `test_parse_invalid_zone_number` | Error for zone 0, 33, "abc" |
| `test_parse_missing_name` | Error reported with row number |
| `test_parse_unknown_type` | Error for unrecognized type |
| `test_atomic_rejection` | Any error → 0 devices returned |
| `test_export_roundtrip` | Export → parse → matches original options |

---

## `pyproject.toml` (Dev Dependencies)

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-homeassistant-custom-component>=0.13",
    "ruff>=0.5",
    "mypy>=1.10",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = true
```

---

## CI Workflow (`.github/workflows/validate.yml`)

```yaml
name: Validate
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra dev
      - run: uv run pytest --cov=custom_components/radiora_classic
  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra dev
      - run: uv run mypy custom_components/radiora_classic
```
