"""Tests for RadioRA Classic event entity (master control buttons)."""

import pytest
from unittest.mock import patch
from datetime import datetime, timezone

from homeassistant.core import HomeAssistant

from custom_components.radiora_classic.coordinator import RadioRACoordinator
from custom_components.radiora_classic.event import RadioRAMasterEvent
from custom_components.radiora_classic.pyradiora_classic import (
    ButtonState, MasterButtonPress, System,
)


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry, mock_radiora_client):
    """Create a coordinator with mocked client."""
    return RadioRACoordinator(
        hass, mock_config_entry,
        url="socket://192.168.1.50:4999", bridged=False,
        controller_id="main_floor", poll_interval=30,
    )


@pytest.fixture
def master_event(coordinator, hass):
    """Create a master control event entity."""
    config = {"master_control": 1, "button": 3, "name": "Kitchen Top", "area": "Kitchen"}
    entity = RadioRAMasterEvent(coordinator, "main_floor", config)
    entity.hass = hass
    return entity


def test_event_types(master_event):
    """Should support 'press' event type."""
    assert master_event.event_types == ["press"]


def test_unique_id(master_event):
    """Unique ID should match spec format."""
    assert master_event.unique_id == "radiora_classic.main_floor.master.mc1.b3"


def test_fires_on_new_press(master_event, coordinator):
    """Should fire event when new MBP timestamp detected."""
    ts1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    coordinator._master_events[(1, 3)] = ts1

    # Simulate coordinator update -- patch async_write_ha_state since entity
    # is not registered with HA in unit tests
    with patch.object(master_event, "async_write_ha_state"):
        master_event._handle_coordinator_update()
    assert master_event._last_seen_ts == ts1


def test_does_not_refire_same_press(master_event, coordinator):
    """Should not fire again for same timestamp."""
    ts1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    coordinator._master_events[(1, 3)] = ts1

    with patch.object(master_event, "async_write_ha_state"):
        master_event._handle_coordinator_update()
    first_ts = master_event._last_seen_ts

    # Call again with same timestamp -- should not fire _trigger_event again
    with patch.object(master_event, "_trigger_event") as mock_trigger:
        with patch.object(master_event, "async_write_ha_state"):
            master_event._handle_coordinator_update()
        mock_trigger.assert_not_called()
    assert master_event._last_seen_ts == first_ts
