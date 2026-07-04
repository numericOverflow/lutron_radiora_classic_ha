"""Tests for RadioRA Classic diagnostics."""

import pytest
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.radiora_classic.diagnostics import async_get_config_entry_diagnostics
from custom_components.radiora_classic.coordinator import RadioRACoordinator
from custom_components.radiora_classic.models import RadioRAData
from custom_components.radiora_classic.pyradiora_classic import System


@pytest.fixture
def coordinator(hass: HomeAssistant, mock_config_entry, mock_radiora_client):
    """Create a coordinator with mocked client."""
    return RadioRACoordinator(
        hass, mock_config_entry,
        url="socket://192.168.1.50:4999", bridged=False,
        controller_id="main_floor", poll_interval=30,
    )


async def test_diagnostics_redacts_url(hass: HomeAssistant, mock_config_entry, coordinator):
    """URL should be redacted in diagnostics output."""
    mock_config_entry.runtime_data = RadioRAData(
        coordinator=coordinator, controller_id="main_floor"
    )
    coordinator._zone_levels[(System.NONE, 1)] = 75

    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    # URL should be redacted
    assert result["entry_data"]["url"] == "**REDACTED**"
    # State should be present
    assert result["state"]["connected"] is True
    assert "z1" in result["state"]["zone_levels"]
