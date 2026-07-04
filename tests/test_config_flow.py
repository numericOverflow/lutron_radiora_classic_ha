"""Tests for RadioRA Classic config flow.

These tests require the full HA runtime (real config entry flow engine).
They are skipped on Windows / when pytest-homeassistant-custom-component
is not installed.
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.radiora_classic.const import DOMAIN
from custom_components.radiora_classic.pyradiora_classic import (
    RadioRAConnectionError,
    RadioRATimeoutError,
    System,
    VersionInfo,
    ZoneMap,
)

pytestmark = pytest.mark.requires_ha_runtime


@pytest.fixture
def mock_try_connection():
    """Mock _try_connection to succeed."""
    with patch(
        "custom_components.radiora_classic.config_flow._try_connection",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture
def mock_discover_zones():
    """Mock _discover_zones to return test zones."""
    with patch(
        "custom_components.radiora_classic.config_flow._discover_zones",
        new_callable=AsyncMock,
    ) as mock:
        mock.return_value = [
            {"zone": 1, "is_on": True, "system": None},
            {"zone": 2, "is_on": True, "system": None},
            {"zone": 5, "is_on": False, "system": None},
        ]
        yield mock


async def test_user_step_success(hass: HomeAssistant, mock_try_connection, mock_discover_zones):
    """Full flow: user step -> discover -> name -> entry created."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Submit connection details
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Main Floor", "url": "socket://192.168.1.50:4999", "bridged": False},
    )
    assert result["step_id"] == "discover_zones"

    # Select zones
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"selected_zones": ["1", "5"]},
    )
    assert result["step_id"] == "name_zones"

    # Name first zone
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Living Room", "mode": "dimmer"},
    )
    assert result["step_id"] == "name_zones"

    # Name second zone
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Porch", "mode": "onoff"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["url"] == "socket://192.168.1.50:4999"
    assert result["options"]["controller_id"] == "main_floor"
    assert len(result["options"]["zones"]) == 2


async def test_user_step_connection_failure(hass: HomeAssistant):
    """Connection failure should show error, not create entry."""
    with patch(
        "custom_components.radiora_classic.config_flow._try_connection",
        new_callable=AsyncMock,
        side_effect=RadioRAConnectionError("refused"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"name": "Test", "url": "socket://192.168.1.50:4999", "bridged": False},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["url"] == "connection_error"


async def test_user_step_duplicate_url(hass: HomeAssistant, mock_config_entry, mock_try_connection):
    """Same URL should abort with already_configured."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Another", "url": "socket://192.168.1.50:4999", "bridged": False},
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_step_invalid_url(hass: HomeAssistant):
    """Invalid URL format should show error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"name": "Test", "url": "http://wrong.com", "bridged": False},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["url"] == "invalid_url"
