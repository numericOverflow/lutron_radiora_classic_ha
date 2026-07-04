"""Tests for RadioRA Classic sensor entity (connection health)."""

import pytest
from datetime import datetime, timezone

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from custom_components.radiora_classic.coordinator import RadioRACoordinator
from custom_components.radiora_classic.sensor import RadioRAConnectionSensor


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry, mock_radiora_client):
    """Create a coordinator with mocked client."""
    return RadioRACoordinator(
        hass, mock_config_entry,
        url="socket://192.168.1.50:4999", bridged=False,
        controller_id="main_floor", poll_interval=30,
    )


@pytest.fixture
def sensor(coordinator):
    """Create a connection sensor."""
    return RadioRAConnectionSensor(coordinator, "main_floor")


def test_entity_category(sensor):
    """Should be a diagnostic entity."""
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


def test_connected_state(sensor, mock_radiora_client):
    """Should report 'connected' when client is connected."""
    mock_radiora_client.connected = True
    assert sensor.native_value == "connected"


def test_disconnected_state(sensor, mock_radiora_client):
    """Should report 'disconnected' when client is not connected."""
    mock_radiora_client.connected = False
    assert sensor.native_value == "disconnected"


def test_extra_attributes(sensor, coordinator):
    """Should include reconnect_count and url."""
    attrs = sensor.extra_state_attributes
    assert "reconnect_count" in attrs
    assert attrs["url"] == "socket://192.168.1.50:4999"


def test_unique_id(sensor):
    """Unique ID should match spec."""
    assert sensor.unique_id == "radiora_classic.main_floor.sensor.connection"


def test_device_info_includes_sw_version(coordinator, mock_radiora_client):
    """DeviceInfo should include firmware version when available."""
    coordinator._firmware_version = "M2.29 / S1.0"
    sensor = RadioRAConnectionSensor(coordinator, "main_floor")
    assert sensor.device_info["sw_version"] == "M2.29 / S1.0"


def test_device_info_sw_version_none_when_not_queried(sensor):
    """DeviceInfo sw_version should be None before first connect."""
    assert sensor.device_info.get("sw_version") is None
