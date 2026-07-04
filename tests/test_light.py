"""Tests for RadioRA Classic light entity."""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_TRANSITION, ColorMode
from homeassistant.core import HomeAssistant

from custom_components.radiora_classic.coordinator import RadioRACoordinator
from custom_components.radiora_classic.light import RadioRALight
from custom_components.radiora_classic.pyradiora_classic import System


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry, mock_radiora_client):
    """Create a coordinator with mocked client."""
    return RadioRACoordinator(
        hass,
        mock_config_entry,
        url="socket://192.168.1.50:4999",
        bridged=False,
        controller_id="main_floor",
        poll_interval=30,
    )


@pytest.fixture
def dimmer_light(coordinator):
    """Create a dimmer light entity."""
    zone_config = {"zone": 1, "name": "Living Room", "mode": "dimmer", "area": "Living Room", "fade_sec": None}
    return RadioRALight(coordinator, "main_floor", zone_config)


@pytest.fixture
def dimmer_light_with_fade(coordinator):
    """Create a dimmer light with configured fade."""
    zone_config = {"zone": 2, "name": "Kitchen", "mode": "dimmer", "area": "Kitchen", "fade_sec": 3}
    return RadioRALight(coordinator, "main_floor", zone_config)


@pytest.fixture
def onoff_light(coordinator):
    """Create an on/off light entity."""
    zone_config = {"zone": 5, "name": "Porch", "mode": "onoff", "area": "Exterior", "fade_sec": None}
    return RadioRALight(coordinator, "main_floor", zone_config)


def test_dimmer_color_mode(dimmer_light):
    """Dimmer should have BRIGHTNESS color mode."""
    assert dimmer_light.supported_color_modes == {ColorMode.BRIGHTNESS}
    assert dimmer_light.color_mode == ColorMode.BRIGHTNESS


def test_onoff_color_mode(onoff_light):
    """On/off light should have ONOFF color mode."""
    assert onoff_light.supported_color_modes == {ColorMode.ONOFF}
    assert onoff_light.color_mode == ColorMode.ONOFF


def test_dimmer_brightness(dimmer_light, coordinator):
    """Brightness should convert 0-100 to 0-255."""
    coordinator._zone_levels[(System.NONE, 1)] = 50
    assert dimmer_light.brightness == 127  # int(50 * 255 / 100)


def test_onoff_no_brightness(onoff_light):
    """On/off light should return None for brightness."""
    assert onoff_light.brightness is None


def test_is_on(dimmer_light, coordinator):
    """is_on should reflect zone level > 0."""
    coordinator._zone_levels[(System.NONE, 1)] = 0
    assert dimmer_light.is_on is False
    coordinator._zone_levels[(System.NONE, 1)] = 50
    assert dimmer_light.is_on is True


async def test_dimmer_turn_on_with_brightness(dimmer_light, coordinator, mock_radiora_client):
    """Turn on with brightness should send correct level."""
    await dimmer_light.async_turn_on(**{ATTR_BRIGHTNESS: 191})
    # 191 * 100 / 255 = 74
    mock_radiora_client.set_dimmer_level.assert_called_once_with(1, 74, None, System.NONE)


async def test_dimmer_turn_on_no_brightness(dimmer_light, coordinator, mock_radiora_client):
    """Turn on without brightness should restore previous level."""
    dimmer_light._prev_level = 60
    await dimmer_light.async_turn_on()
    mock_radiora_client.set_dimmer_level.assert_called_once_with(1, 60, None, System.NONE)


async def test_dimmer_turn_on_with_transition(dimmer_light, coordinator, mock_radiora_client):
    """Turn on with transition should pass fade_sec."""
    await dimmer_light.async_turn_on(**{ATTR_BRIGHTNESS: 255, ATTR_TRANSITION: 5.0})
    mock_radiora_client.set_dimmer_level.assert_called_once_with(1, 100, 5, System.NONE)


async def test_dimmer_fade_from_config(dimmer_light_with_fade, coordinator, mock_radiora_client):
    """Should use zone config fade_sec when no transition kwarg."""
    await dimmer_light_with_fade.async_turn_on(**{ATTR_BRIGHTNESS: 128})
    mock_radiora_client.set_dimmer_level.assert_called_once_with(2, 50, 3, System.NONE)


async def test_dimmer_no_fade_default(dimmer_light, coordinator, mock_radiora_client):
    """Should omit fade when neither config nor kwarg set."""
    await dimmer_light.async_turn_on(**{ATTR_BRIGHTNESS: 128})
    mock_radiora_client.set_dimmer_level.assert_called_once_with(1, 50, None, System.NONE)


async def test_dimmer_turn_off(dimmer_light, coordinator, mock_radiora_client):
    """Turn off should send level 0."""
    coordinator._zone_levels[(System.NONE, 1)] = 75
    await dimmer_light.async_turn_off()
    mock_radiora_client.set_dimmer_level.assert_called_once_with(1, 0, None, System.NONE)


async def test_dimmer_turn_off_preserves_prev_level(dimmer_light, coordinator, mock_radiora_client):
    """Turn off should save current level for restore."""
    coordinator._zone_levels[(System.NONE, 1)] = 80
    await dimmer_light.async_turn_off()
    assert dimmer_light._prev_level == 80


async def test_onoff_turn_on(onoff_light, coordinator, mock_radiora_client):
    """On/off turn on should send SSL ON."""
    await onoff_light.async_turn_on()
    mock_radiora_client.switch_on.assert_called_once_with(5, system=System.NONE)


async def test_onoff_turn_off(onoff_light, coordinator, mock_radiora_client):
    """On/off turn off should send SSL OFF."""
    await onoff_light.async_turn_off()
    mock_radiora_client.switch_off.assert_called_once_with(5, system=System.NONE)


def test_unique_id_format(dimmer_light):
    """Unique ID should follow spec format."""
    assert dimmer_light.unique_id == "radiora_classic.main_floor.light.z1"


def test_device_info(dimmer_light):
    """Device info should have correct identifiers and name."""
    info = dimmer_light.device_info
    assert info["identifiers"] == {("radiora_classic", "main_floor.light.z1")}
    assert info["name"] == "Living Room"
    assert info["manufacturer"] == "Lutron"
    assert info["suggested_area"] == "Living Room"
