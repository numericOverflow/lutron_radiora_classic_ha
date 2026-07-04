"""Tests for RadioRA Classic switch entity (phantom buttons)."""

import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone

from homeassistant.core import HomeAssistant

from custom_components.radiora_classic.coordinator import RadioRACoordinator
from custom_components.radiora_classic.switch import RadioRAPhantomSwitch
from custom_components.radiora_classic.pyradiora_classic import ButtonState, System


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry, mock_radiora_client):
    """Create a coordinator with mocked client."""
    return RadioRACoordinator(
        hass, mock_config_entry,
        url="socket://192.168.1.50:4999", bridged=False,
        controller_id="main_floor", poll_interval=30,
    )


@pytest.fixture
def phantom_switch(coordinator):
    """Create a phantom button switch entity."""
    config = {"button": 1, "name": "Evening Scene", "area": "Living Room"}
    return RadioRAPhantomSwitch(coordinator, "main_floor", config)


def test_phantom_is_on(phantom_switch, coordinator):
    """is_on should reflect phantom state cache."""
    coordinator._phantom_states[1] = True
    assert phantom_switch.is_on is True
    coordinator._phantom_states[1] = False
    assert phantom_switch.is_on is False


async def test_phantom_turn_on(phantom_switch, coordinator, mock_radiora_client):
    """Turn on should send BP,button,ON."""
    await phantom_switch.async_turn_on()
    mock_radiora_client.button_press.assert_called_once_with(
        1, ButtonState.ON, system=System.NONE
    )


async def test_phantom_turn_off(phantom_switch, coordinator, mock_radiora_client):
    """Turn off should send BP,button,OFF."""
    await phantom_switch.async_turn_off()
    mock_radiora_client.button_press.assert_called_once_with(
        1, ButtonState.OFF, system=System.NONE
    )


def test_unique_id(phantom_switch):
    """Unique ID should match spec format."""
    assert phantom_switch.unique_id == "radiora_classic.main_floor.phantom.b1"
