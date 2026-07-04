"""Tests for RadioRA Classic button entity (ALL ON / ALL OFF)."""

import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone

from homeassistant.core import HomeAssistant

from custom_components.radiora_classic.coordinator import RadioRACoordinator
from custom_components.radiora_classic.button import RadioRASystemButton
from custom_components.radiora_classic.pyradiora_classic import (
    BUTTON_ALL_ON, BUTTON_ALL_OFF, ButtonState, System,
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
def all_on_button(coordinator):
    """Create ALL ON button entity."""
    return RadioRASystemButton(coordinator, "main_floor", BUTTON_ALL_ON, "All On")


@pytest.fixture
def all_off_button(coordinator):
    """Create ALL OFF button entity."""
    return RadioRASystemButton(coordinator, "main_floor", BUTTON_ALL_OFF, "All Off")


async def test_all_on_press(all_on_button, mock_radiora_client):
    """ALL ON should send BP,16,ON."""
    await all_on_button.async_press()
    mock_radiora_client.button_press.assert_called_once_with(
        BUTTON_ALL_ON, ButtonState.ON, system=System.NONE
    )


async def test_all_off_press(all_off_button, mock_radiora_client):
    """ALL OFF should send BP,17,OFF."""
    await all_off_button.async_press()
    mock_radiora_client.button_press.assert_called_once_with(
        BUTTON_ALL_OFF, ButtonState.OFF, system=System.NONE
    )


def test_unique_ids(all_on_button, all_off_button):
    """Unique IDs should match spec."""
    assert all_on_button.unique_id == "radiora_classic.main_floor.button.all_on"
    assert all_off_button.unique_id == "radiora_classic.main_floor.button.all_off"
