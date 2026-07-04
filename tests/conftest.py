"""Shared test fixtures for RadioRA Classic integration tests.

Hybrid test setup:
- On all platforms: tests run against a mock HomeAssistant object.
  Most entity/coordinator tests work fine this way.
- On Linux with `pytest-homeassistant-custom-component` installed:
  tests marked @pytest.mark.requires_ha_runtime use the real HA test
  harness (real config entry flows, registries, etc.).

To run on Windows:
    uv run --extra dev pytest tests/ -v

To run full suite on Linux (CI or WSL):
    uv run --extra dev-full pytest tests/ -v
"""

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from custom_components.radiora_classic.const import DOMAIN

# Detect whether the full HA test runtime is available
try:
    import pytest_homeassistant_custom_component  # noqa: F401
    _HAS_HA_RUNTIME = True
except ImportError:
    _HAS_HA_RUNTIME = False

IS_WINDOWS = sys.platform == "win32"


def pytest_configure(config):
    """Register custom markers and print platform warnings."""
    config.addinivalue_line(
        "markers",
        "requires_ha_runtime: test requires full Home Assistant runtime (Linux only)",
    )


def pytest_collection_modifyitems(config, items):
    """Skip requires_ha_runtime tests when the full harness is not available."""
    if _HAS_HA_RUNTIME:
        return

    skip_marker = pytest.mark.skip(
        reason="requires pytest-homeassistant-custom-component (Linux only)"
    )
    skipped = []
    for item in items:
        if "requires_ha_runtime" in item.keywords:
            item.add_marker(skip_marker)
            skipped.append(item.name)

    if skipped:
        print(
            f"\n[WARNING] Skipping {len(skipped)} test(s) that require the full HA runtime.\n"
            f"   These tests exercise config flows and entry lifecycle that need\n"
            f"   pytest-homeassistant-custom-component (Linux only).\n"
            f"   For full coverage, re-run on Linux/WSL:\n"
            f"     uv run --extra dev-full pytest tests/ -v\n"
        )


def pytest_sessionfinish(session, exitstatus):
    """Print reminder at end of session if tests were skipped due to platform."""
    if not _HAS_HA_RUNTIME:
        skipped_count = sum(
            1 for item in session.items
            if "requires_ha_runtime" in item.keywords
        )
        if skipped_count:
            print(
                f"\n{'='*70}\n"
                f"  [INFO] {skipped_count} test(s) skipped (require full HA runtime).\n"
                f"  For complete coverage, run on Linux/WSL with:\n"
                f"    uv run --extra dev-full pytest tests/ -v\n"
                f"{'='*70}\n"
            )


# =============================================================================
# hass fixture: real or mock depending on environment
# =============================================================================


if _HAS_HA_RUNTIME:
    # The pytest-homeassistant-custom-component plugin provides the real `hass`
    # fixture automatically. We don't need to define it here.
    pass
else:
    @pytest.fixture
    def hass():
        """Minimal mock HomeAssistant for unit tests without full HA runtime."""
        mock_hass = MagicMock(spec=HomeAssistant)
        mock_hass.data = {}
        mock_hass.config_entries = MagicMock()
        mock_hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
        mock_hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        mock_hass.config_entries.async_loaded_entries = MagicMock(return_value=[])
        mock_hass.bus = MagicMock()
        mock_hass.bus.async_listen_once = MagicMock(return_value=lambda: None)
        mock_hass.async_create_task = MagicMock(side_effect=lambda coro: coro)
        mock_hass.loop = MagicMock()
        # Needed by DataUpdateCoordinator
        mock_hass.async_add_job = MagicMock()
        mock_hass.async_create_background_task = MagicMock()
        return mock_hass


@pytest.fixture
def mock_config_entry() -> ConfigEntry:
    """Create a mock config entry with typical options."""
    from types import MappingProxyType

    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="main_floor",
        data={"url": "socket://192.168.1.50:4999", "bridged": False},
        source="user",
        unique_id="socket://192.168.1.50:4999",
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
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
    return entry


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
        client.connected_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        client.last_message_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        client.reconnect_count = 0
        client.url = "socket://192.168.1.50:4999"

        # Default zone map: zones 1,2 ON, zone 5 OFF, rest unassigned
        from custom_components.radiora_classic.pyradiora_classic import (
            ZoneMap, LEDMap, VersionInfo, System,
        )
        zone_map = ZoneMap(
            raw="ZMP,11000XXXXXXXXXXXXXXXXXXXXXXXXXXX",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            states="11000" + "X" * 27,
            system=System.NONE,
        )
        client.get_zone_map = AsyncMock(return_value=[zone_map])

        # Default LED map: button 1 active, rest off
        led_map = LEDMap(
            raw="LMP,100000000000000",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            bitmap="100000000000000",
        )
        client.get_led_map = AsyncMock(return_value=led_map)

        # Version
        client.get_version = AsyncMock(return_value=VersionInfo(
            raw="REV,1.0,1.0",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            master_version="1.0",
            slave_version="1.0",
        ))

        # Commands are fire-and-forget
        client.set_dimmer_level = AsyncMock()
        client.switch_on = AsyncMock()
        client.switch_off = AsyncMock()
        client.button_press = AsyncMock()
        client.start_polling = AsyncMock()
        client.stop_polling = AsyncMock()
        client.start_monitoring = AsyncMock()
        client._send = AsyncMock()

        yield client
