"""Tests for RadioRA Classic client wrapper."""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from custom_components.radiora_classic.client import RadioRAClientWrapper
from custom_components.radiora_classic.pyradiora_classic import (
    ButtonState, System, ZoneMap,
)


@pytest.fixture
def wrapper(mock_radiora_client):
    """Create a client wrapper with mocked underlying client."""
    callback = lambda msg: None
    w = RadioRAClientWrapper("socket://192.168.1.50:4999", False, callback)
    return w


async def test_connect(wrapper, mock_radiora_client):
    """connect() should delegate to library client."""
    await wrapper.connect()
    mock_radiora_client.connect.assert_called_once()


async def test_start(wrapper, mock_radiora_client):
    """start() should delegate to library client."""
    await wrapper.start()
    mock_radiora_client.start.assert_called_once()


async def test_stop(wrapper, mock_radiora_client):
    """stop() should delegate to library client."""
    await wrapper.stop()
    mock_radiora_client.stop.assert_called_once()


async def test_set_dimmer_level(wrapper, mock_radiora_client):
    """set_dimmer_level should pass through to library."""
    await wrapper.set_dimmer_level(3, 75, 5, System.NONE)
    mock_radiora_client.set_dimmer_level.assert_called_once_with(3, 75, 5, System.NONE)


async def test_switch_on(wrapper, mock_radiora_client):
    """switch_on should pass through."""
    await wrapper.switch_on(5, System.S1)
    mock_radiora_client.switch_on.assert_called_once_with(5, system=System.S1)


async def test_button_press(wrapper, mock_radiora_client):
    """button_press should pass through."""
    await wrapper.button_press(1, ButtonState.ON, System.NONE)
    mock_radiora_client.button_press.assert_called_once_with(1, ButtonState.ON, system=System.NONE)


def test_connected_property(wrapper, mock_radiora_client):
    """connected should delegate to library."""
    mock_radiora_client.connected = True
    assert wrapper.connected is True
    mock_radiora_client.connected = False
    assert wrapper.connected is False


def test_reconnect_count(wrapper, mock_radiora_client):
    """reconnect_count should delegate to library."""
    mock_radiora_client.reconnect_count = 3
    assert wrapper.reconnect_count == 3
