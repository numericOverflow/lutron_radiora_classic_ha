"""Tests for RadioRA Classic coordinator."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.radiora_classic.coordinator import RadioRACoordinator
from custom_components.radiora_classic.pyradiora_classic import (
    ButtonState,
    LEDMap,
    LocalZoneChange,
    MasterButtonPress,
    RadioRAConnectionError,
    RadioRAConnectionLost,
    RadioRATimeoutError,
    System,
    ZoneMap,
    ZoneState,
)


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry, mock_radiora_client):
    """Create a coordinator with mocked client."""
    coord = RadioRACoordinator(
        hass,
        mock_config_entry,
        url="socket://192.168.1.50:4999",
        bridged=False,
        controller_id="main_floor",
        poll_interval=30,
    )
    return coord


async def test_first_refresh_connects(coordinator, mock_radiora_client):
    """First refresh should call start() and query state."""
    mock_radiora_client.connected = False
    await coordinator._async_update_data()
    mock_radiora_client.start.assert_called_once()


async def test_poll_updates_zone_states(coordinator, mock_radiora_client):
    """ZMP response should update zone levels cache."""
    data = await coordinator._async_update_data()
    # Zones 1,2 are ON (level 100), zone 5 is OFF (level 0)
    assert coordinator.get_zone_level(1) == 100
    assert coordinator.get_zone_level(2) == 100
    assert coordinator.get_zone_level(5) == 0


async def test_poll_updates_phantom_states(coordinator, mock_radiora_client):
    """LMP response should update phantom button cache."""
    await coordinator._async_update_data()
    assert coordinator.get_phantom_state(1) is True
    assert coordinator.get_phantom_state(2) is False


async def test_push_lzc_on(coordinator):
    """LZC ON message should set zone level to 100."""
    msg = LocalZoneChange(
        raw="LZC,03,ON",
        timestamp=datetime.now(timezone.utc),
        zone=3,
        state=ZoneState.ON,
        system=System.NONE,
    )
    coordinator._handle_message(msg)
    assert coordinator.get_zone_level(3) == 100


async def test_push_lzc_off(coordinator):
    """LZC OFF message should set zone level to 0."""
    # First set it to something non-zero
    coordinator._zone_levels[(System.NONE, 3)] = 75
    msg = LocalZoneChange(
        raw="LZC,03,OFF",
        timestamp=datetime.now(timezone.utc),
        zone=3,
        state=ZoneState.OFF,
        system=System.NONE,
    )
    coordinator._handle_message(msg)
    assert coordinator.get_zone_level(3) == 0


async def test_push_lzc_chg_preserves_level(coordinator):
    """LZC CHG message should preserve existing level."""
    coordinator._zone_levels[(System.NONE, 3)] = 75
    msg = LocalZoneChange(
        raw="LZC,03,CHG",
        timestamp=datetime.now(timezone.utc),
        zone=3,
        state=ZoneState.CHG,
        system=System.NONE,
    )
    coordinator._handle_message(msg)
    assert coordinator.get_zone_level(3) == 75


async def test_push_mbp(coordinator):
    """MBP message should update master events timestamp."""
    ts = datetime.now(timezone.utc)
    msg = MasterButtonPress(
        raw="MBP,1,3,ON",
        timestamp=ts,
        master_control=1,
        button=3,
        state=ButtonState.ON,
        system=System.NONE,
    )
    coordinator._handle_message(msg)
    assert coordinator.get_master_last_press(1, 3) == ts


async def test_optimistic_dimmer(coordinator, mock_radiora_client):
    """async_set_dimmer should update cache before sending command."""
    await coordinator.async_set_dimmer(3, 75, None, System.NONE)
    assert coordinator.get_zone_level(3) == 75
    mock_radiora_client.set_dimmer_level.assert_called_once_with(3, 75, None, System.NONE)


async def test_optimistic_switch(coordinator, mock_radiora_client):
    """async_switch_zone should update cache before sending command."""
    await coordinator.async_switch_zone(5, True, System.NONE)
    assert coordinator.get_zone_level(5) == 100
    mock_radiora_client.switch_on.assert_called_once_with(5, system=System.NONE)

    await coordinator.async_switch_zone(5, False, System.NONE)
    assert coordinator.get_zone_level(5) == 0
    mock_radiora_client.switch_off.assert_called_once_with(5, system=System.NONE)


async def test_zmp_does_not_clobber_optimistic_level(coordinator):
    """ZMP ON should not overwrite existing tracked level."""
    # Simulate optimistic update to 75%
    coordinator._zone_levels[(System.NONE, 1)] = 75

    # ZMP says zone 1 is ON -- should preserve 75, not overwrite to 100
    zm = ZoneMap(
        raw="ZMP,11001XXXXXXXXXXXXXXXXXXXXXXXXXXX",
        timestamp=datetime.now(timezone.utc),
        states="11001" + "X" * 27,
        system=System.NONE,
    )
    coordinator._handle_zone_map(zm)
    assert coordinator.get_zone_level(1) == 75


async def test_zmp_sets_100_for_unknown_on_zone(coordinator):
    """ZMP ON with no tracked level should assume 100%."""
    zm = ZoneMap(
        raw="ZMP,10000XXXXXXXXXXXXXXXXXXXXXXXXXXX",
        timestamp=datetime.now(timezone.utc),
        states="10000" + "X" * 27,
        system=System.NONE,
    )
    coordinator._handle_zone_map(zm)
    assert coordinator.get_zone_level(1) == 100


async def test_connection_error_raises_not_ready(coordinator, mock_radiora_client):
    """Connection error on first refresh should raise ConfigEntryNotReady."""
    mock_radiora_client.connected = False
    mock_radiora_client.start = AsyncMock(
        side_effect=RadioRAConnectionError("refused")
    )
    with pytest.raises(ConfigEntryNotReady):
        await coordinator._async_update_data()


async def test_timeout_raises_update_failed(coordinator, mock_radiora_client):
    """Timeout during poll should raise UpdateFailed."""
    mock_radiora_client.get_zone_map = AsyncMock(
        side_effect=RadioRATimeoutError("no response")
    )
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_firmware_version_queried_on_first_connect(coordinator, mock_radiora_client):
    """Firmware version should be queried and cached on first connect."""
    mock_radiora_client.connected = False
    await coordinator._async_update_data()
    mock_radiora_client.get_version.assert_called_once()
    assert coordinator.firmware_version == "1.0 / 1.0"


async def test_firmware_version_failure_non_fatal(coordinator, mock_radiora_client):
    """Firmware version query failure should not break setup."""
    mock_radiora_client.connected = False
    mock_radiora_client.get_version = AsyncMock(
        side_effect=RadioRATimeoutError("no response")
    )
    await coordinator._async_update_data()
    assert coordinator.firmware_version is None


async def test_lmp_timeout_non_fatal(coordinator, mock_radiora_client):
    """LMP query timeout should not fail the entire poll."""
    mock_radiora_client.get_led_map = AsyncMock(
        side_effect=RadioRATimeoutError("no response")
    )
    # Should not raise -- LMP failure is caught internally
    data = await coordinator._async_update_data()
    assert data is not None
