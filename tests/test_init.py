"""Tests for RadioRA Classic entry setup/unload lifecycle.

These tests require the full HA runtime (real config entry registry).
They are skipped on Windows / when pytest-homeassistant-custom-component
is not installed.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from homeassistant.core import HomeAssistant

from custom_components.radiora_classic import async_setup_entry, async_unload_entry
from custom_components.radiora_classic.const import DOMAIN

pytestmark = pytest.mark.requires_ha_runtime


async def test_setup_entry(hass: HomeAssistant, mock_config_entry, mock_radiora_client):
    """Entry setup should create coordinator and forward platforms."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.radiora_classic.RadioRACoordinator.async_config_entry_first_refresh",
        new_callable=AsyncMock,
    ):
        result = await async_setup_entry(hass, mock_config_entry)

    assert result is True
    assert mock_config_entry.runtime_data is not None
    assert mock_config_entry.runtime_data.controller_id == "main_floor"


async def test_unload_entry(hass: HomeAssistant, mock_config_entry, mock_radiora_client):
    """Entry unload should stop coordinator and unload platforms."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.radiora_classic.RadioRACoordinator.async_config_entry_first_refresh",
        new_callable=AsyncMock,
    ):
        await async_setup_entry(hass, mock_config_entry)

    with patch.object(
        hass.config_entries, "async_unload_platforms", new_callable=AsyncMock, return_value=True
    ):
        result = await async_unload_entry(hass, mock_config_entry)

    assert result is True
