"""Command string builders for Lutron RadioRA Classic RS-232 protocol.

All functions return a str (the raw command without CR terminator —
transport appends it). Per 044-038a spec.
"""

from .const import (
    BUTTON_ALL_OFF,
    BUTTON_ALL_ON,
    MAX_DELAY_SECONDS,
    MAX_DIMMER_LEVEL,
    MAX_FADE_SECONDS,
    MAX_PHANTOM_BUTTONS,
    MAX_ZONES,
    ButtonState,
    MonitorType,
    SwitchState,
    System,
)


def _validate_zone(zone: int) -> None:
    if zone < 1 or zone > MAX_ZONES:
        raise ValueError(f"zone must be 1-{MAX_ZONES}, got {zone}")


def _validate_button(button: int) -> None:
    if button < 1 or button > BUTTON_ALL_OFF:
        raise ValueError(f"button must be 1-{BUTTON_ALL_OFF}, got {button}")


def _validate_range(value: int, min_val: int, max_val: int, name: str) -> None:
    if value < min_val or value > max_val:
        raise ValueError(f"{name} must be {min_val}-{max_val}, got {value}")


def _append_system(parts: list[str], system: System) -> None:
    if system != System.NONE:
        parts.append(f"S{system.value}")


def set_dimmer_level(
    zone: int,
    level: int,
    fade_sec: int | None = None,
    system: System = System.NONE,
) -> str:
    """Build SDL or SFA command depending on whether fade is specified.

    Args:
        zone: Zone number (1-32)
        level: Brightness 0 (off) to 100 (full)
        fade_sec: If None or 0, uses SDL (instant). If >0, uses SFA (fade).
        system: System for bridged configurations

    Returns:
        Command string:
        - 'SDL,3,75' (instant, no fade)
        - 'SDL,3,75,S1' (instant, bridged system 1)
        - 'SFA,3,75,5' (fade to 75% over 5 seconds)
        - 'SFA,3,75,5,S2' (fade, bridged system 2)
    """
    _validate_zone(zone)
    _validate_range(level, 0, MAX_DIMMER_LEVEL, "level")

    if fade_sec is not None and fade_sec > 0:
        _validate_range(fade_sec, 1, MAX_FADE_SECONDS, "fade_sec")
        parts: list[str] = ["SFA", str(zone), str(level), str(fade_sec)]
    else:
        parts = ["SDL", str(zone), str(level)]

    _append_system(parts, system)
    return ",".join(parts)


def set_switch_level(
    zone: int,
    state: SwitchState,
    delay_sec: int | None = None,
    system: System = System.NONE,
) -> str:
    """Build SSL (Set Switch Level) command.

    Args:
        zone: Zone number (1-32)
        state: SwitchState.ON or SwitchState.OFF
        delay_sec: Optional delay before execution (0-240 seconds)
        system: System for bridged configurations

    Returns:
        Command string, e.g. 'SSL,5,ON' or 'SSL,3,OFF,10,S2'
    """
    _validate_zone(zone)
    if delay_sec is not None:
        _validate_range(delay_sec, 0, MAX_DELAY_SECONDS, "delay_sec")

    parts: list[str] = ["SSL", str(zone), state.value]
    if delay_sec is not None:
        parts.append(str(delay_sec))
    _append_system(parts, system)
    return ",".join(parts)


def button_press(
    button: int,
    state: ButtonState,
    fade_sec: int | None = None,
    system: System = System.NONE,
) -> str:
    """Build BP (Button Press) command for phantom buttons.

    Args:
        button: Button number 1-17 (1-15 phantom, 16=ALL ON, 17=ALL OFF)
        state: ON, OFF, or TOG
        fade_sec: Optional fade for associated dimmers (0-240)
        system: System for bridged configurations
    """
    _validate_button(button)
    if fade_sec is not None:
        _validate_range(fade_sec, 0, MAX_FADE_SECONDS, "fade_sec")

    parts: list[str] = ["BP", str(button), state.value]
    if fade_sec is not None:
        parts.append(str(fade_sec))
    _append_system(parts, system)
    return ",".join(parts)


def raise_button(button: int, system: System = System.NONE) -> str:
    """Build RAISE command for phantom button hold-ramp."""
    _validate_button(button)
    parts: list[str] = ["RAISE", str(button)]
    _append_system(parts, system)
    return ",".join(parts)


def lower_button(button: int, system: System = System.NONE) -> str:
    """Build LOWER command for phantom button hold-ramp."""
    _validate_button(button)
    parts: list[str] = ["LOWER", str(button)]
    _append_system(parts, system)
    return ",".join(parts)


def stop_raise_lower() -> str:
    """Build STOPRL command."""
    return "STOPRL"


def zone_map_inquiry(system: System = System.NONE) -> str:
    """Build ZMPI command."""
    parts: list[str] = ["ZMPI"]
    _append_system(parts, system)
    return ",".join(parts)


def phantom_led_status() -> str:
    """Build LMPI command (LED Map Inquiry)."""
    return "LMPI"


def version_inquiry() -> str:
    """Build VERI command."""
    return "VERI"


def enable_monitoring(monitor_type: MonitorType) -> str:
    """Build monitoring enable command (e.g. LZCMON, MBPMON, ZMPMON)."""
    return f"{monitor_type.value}ON"


def disable_monitoring(monitor_type: MonitorType) -> str:
    """Build monitoring disable command (e.g. LZCMOFF, MBPMOFF, ZMPMOFF)."""
    return f"{monitor_type.value}OFF"


def flash_on() -> str:
    """Build SFM,16,ON (flash all zones)."""
    return f"SFM,{BUTTON_ALL_ON},ON"


def flash_off() -> str:
    """Build SFM,17,OFF (stop flash)."""
    return f"SFM,{BUTTON_ALL_OFF},OFF"


def prompt_on() -> str:
    """Build PON command (enable '!' ready prompts)."""
    return "PON"


def prompt_off() -> str:
    """Build POFF command (disable '!' ready prompts)."""
    return "POFF"
