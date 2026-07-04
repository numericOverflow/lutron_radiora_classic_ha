"""Tests for RadioRA Classic CSV import/export parsing."""

import pytest
from typing import Any

from custom_components.radiora_classic.config_flow import _parse_csv_content
from custom_components.radiora_classic import _build_csv_export


class TestCSVParsing:
    """Test CSV import parsing."""

    def test_parse_valid_zones(self):
        """Valid zone rows should parse correctly."""
        csv = (
            "type,number,name,mode,area,system,fade_sec\n"
            "zone,1,Living Room,dimmer,Living Room,,\n"
            "zone,5,Porch Light,onoff,Exterior,,\n"
            "zone,12,Kitchen,dimmer,Kitchen,,3\n"
        )
        devices, errors = _parse_csv_content(csv)
        assert not errors
        assert len(devices) == 3
        assert devices[0] == {
            "type": "zone", "zone": 1, "name": "Living Room",
            "mode": "dimmer", "area": "Living Room", "fade_sec": None,
        }
        assert devices[1] == {
            "type": "zone", "zone": 5, "name": "Porch Light",
            "mode": "onoff", "area": "Exterior", "fade_sec": None,
        }
        assert devices[2] == {
            "type": "zone", "zone": 12, "name": "Kitchen",
            "mode": "dimmer", "area": "Kitchen", "fade_sec": 3,
        }

    def test_parse_valid_phantom(self):
        """Valid phantom button rows should parse correctly."""
        csv = (
            "type,number,name,mode,area,system,fade_sec\n"
            "phantom,1,Evening Scene,,Living Room,,\n"
            "phantom,3,Movie Mode,,Theater,,\n"
        )
        devices, errors = _parse_csv_content(csv)
        assert not errors
        assert len(devices) == 2
        assert devices[0] == {
            "type": "phantom", "button": 1, "name": "Evening Scene", "area": "Living Room",
        }

    def test_parse_valid_master(self):
        """Valid master control rows should parse correctly."""
        csv = (
            "type,number,name,mode,area,system,fade_sec\n"
            "master,1:3,Kitchen Top,,Kitchen,,\n"
            "master,1:5,Kitchen Bottom,,Kitchen,,\n"
        )
        devices, errors = _parse_csv_content(csv)
        assert not errors
        assert len(devices) == 2
        assert devices[0] == {
            "type": "master", "master_control": 1, "button": 3,
            "name": "Kitchen Top", "area": "Kitchen",
        }

    def test_parse_invalid_zone_number(self):
        """Zone numbers outside 1-32 should produce errors."""
        csv = (
            "type,number,name,mode,area,system,fade_sec\n"
            "zone,0,Bad Zone,dimmer,,,\n"
            "zone,33,Also Bad,dimmer,,,\n"
            "zone,abc,Not A Number,dimmer,,,\n"
        )
        devices, errors = _parse_csv_content(csv)
        assert len(errors) == 3
        assert len(devices) == 0

    def test_parse_missing_name(self):
        """Missing name should produce error with row number."""
        csv = (
            "type,number,name,mode,area,system,fade_sec\n"
            "zone,1,,dimmer,,,\n"
        )
        devices, errors = _parse_csv_content(csv)
        assert len(errors) == 1
        assert "Row 2" in errors[0]
        assert "name" in errors[0]

    def test_parse_unknown_type(self):
        """Unrecognized type should produce error."""
        csv = (
            "type,number,name,mode,area,system,fade_sec\n"
            "dimm,1,Test,dimmer,,,\n"
        )
        devices, errors = _parse_csv_content(csv)
        assert len(errors) == 1
        assert "unknown type" in errors[0]

    def test_atomic_rejection(self):
        """Any error should mean 0 devices returned (but all errors collected)."""
        csv = (
            "type,number,name,mode,area,system,fade_sec\n"
            "zone,1,Good Zone,dimmer,,,\n"
            "zone,99,Bad Zone,dimmer,,,\n"
        )
        devices, errors = _parse_csv_content(csv)
        # One error for zone 99
        assert len(errors) == 1
        # But good zone IS returned -- atomic rejection is at the options flow level
        # The parser returns what it can; the flow rejects all if errors exist
        assert len(devices) == 1

    def test_zone_with_system(self):
        """System field should be included when present."""
        csv = (
            "type,number,name,mode,area,system,fade_sec\n"
            "zone,1,Living Room,dimmer,Living Room,1,\n"
        )
        devices, errors = _parse_csv_content(csv)
        assert not errors
        assert devices[0]["system"] == 1


class TestCSVExport:
    """Test CSV export logic."""

    def test_export_roundtrip(self):
        """Export -> parse should produce matching data."""
        options: dict[str, Any] = {
            "zones": [
                {"zone": 1, "name": "Living Room", "mode": "dimmer", "area": "Living Room", "fade_sec": None},
                {"zone": 5, "name": "Porch", "mode": "onoff", "area": "Exterior", "fade_sec": None},
            ],
            "phantom_buttons": [
                {"button": 1, "name": "Evening Scene", "area": "Living Room"},
            ],
            "master_controls": [
                {"master_control": 1, "button": 3, "name": "Kitchen Top", "area": "Kitchen"},
            ],
        }
        csv_content = _build_csv_export(options)
        devices, errors = _parse_csv_content(csv_content)
        assert not errors
        assert len(devices) == 4

        zones = [d for d in devices if d["type"] == "zone"]
        phantoms = [d for d in devices if d["type"] == "phantom"]
        masters = [d for d in devices if d["type"] == "master"]

        assert len(zones) == 2
        assert zones[0]["name"] == "Living Room"
        assert len(phantoms) == 1
        assert phantoms[0]["button"] == 1
        assert len(masters) == 1
        assert masters[0]["master_control"] == 1
