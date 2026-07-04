# Phase 4: Entity Platform Implementations

## `light.py` — Zone Lights

Single class handles both dimmer (BRIGHTNESS) and on/off (ONOFF) zones based on config.

### Class: `RadioRALight`

```python
class RadioRALight(CoordinatorEntity[RadioRACoordinator], LightEntity):

    def __init__(self, coordinator: RadioRACoordinator, controller_id: str, zone_config: dict) -> None:
        super().__init__(coordinator)
        self._zone = zone_config["zone"]
        self._system = System(zone_config["system"]) if "system" in zone_config else System.NONE
        self._fade_sec = zone_config.get("fade_sec")  # None = omit from command
        self._mode = zone_config.get("mode", "dimmer")
        self._prev_level: int = 100  # last non-zero brightness for restore on turn_on

        # ColorMode based on user config
        if self._mode == "onoff":
            self._attr_color_mode = ColorMode.ONOFF
            self._attr_supported_color_modes = {ColorMode.ONOFF}
        else:
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

        # Entity naming (follows HWI_HA pattern)
        self._attr_has_entity_name = True
        self._attr_name = None
        self._attr_unique_id = f"radiora_classic.{controller_id}.light.z{self._zone}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}.light.z{self._zone}")},
            name=zone_config["name"],
            manufacturer="Lutron",
            model="RadioRA Classic Zone",
        )
        if zone_config.get("area"):
            self._attr_device_info["suggested_area"] = zone_config["area"]

    @property
    def brightness(self) -> int | None:
        if self._mode == "onoff":
            return None
        level = self.coordinator.get_zone_level(self._zone, self._system)
        return int(level * 255 / 100)

    @property
    def is_on(self) -> bool:
        return self.coordinator.get_zone_level(self._zone, self._system) > 0

    async def async_turn_on(self, **kwargs) -> None:
        fade = kwargs.get(ATTR_TRANSITION)
        if fade is None:
            fade = self._fade_sec  # may still be None → omit from command

        if self._mode == "onoff":
            await self.coordinator.async_switch_zone(self._zone, True, self._system)
        elif ATTR_BRIGHTNESS in kwargs:
            level = int(kwargs[ATTR_BRIGHTNESS] * 100 / 255)
            self._prev_level = level
            await self.coordinator.async_set_dimmer(self._zone, level, fade, self._system)
        else:
            # Restore previous brightness (not always 100%)
            await self.coordinator.async_set_dimmer(self._zone, self._prev_level, fade, self._system)

    async def async_turn_off(self, **kwargs) -> None:
        fade = kwargs.get(ATTR_TRANSITION)
        if fade is None:
            fade = self._fade_sec

        # Preserve current level for restore on next turn_on
        current = self.coordinator.get_zone_level(self._zone, self._system)
        if current > 0:
            self._prev_level = current

        if self._mode == "onoff":
            await self.coordinator.async_switch_zone(self._zone, False, self._system)
        else:
            await self.coordinator.async_set_dimmer(self._zone, 0, fade, self._system)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
```

### `async_setup_entry`

```python
async def async_setup_entry(
    hass: HomeAssistant,
    entry: RadioRAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    data = entry.runtime_data
    coordinator = data.coordinator
    controller_id = entry.options["controller_id"]
    entities = [
        RadioRALight(coordinator, controller_id, zone_config)
        for zone_config in entry.options.get("zones", [])
    ]
    async_add_entities(entities)
```

---

## `switch.py` — Phantom Buttons (1-15)

Phantom buttons have LED feedback (on = scene active). Exposed as switches with toggle capability.

### Class: `RadioRAPhantomSwitch`

```python
class RadioRAPhantomSwitch(CoordinatorEntity[RadioRACoordinator], SwitchEntity):

    def __init__(self, coordinator, controller_id, button_config):
        super().__init__(coordinator)
        self._button = button_config["button"]

        self._attr_has_entity_name = True
        self._attr_name = None
        self._attr_unique_id = f"radiora_classic.{controller_id}.phantom.b{self._button}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}.phantom.b{self._button}")},
            name=button_config["name"],
            manufacturer="Lutron",
            model="RadioRA Classic Phantom Button",
        )
        if button_config.get("area"):
            self._attr_device_info["suggested_area"] = button_config["area"]

    @property
    def is_on(self) -> bool:
        return self.coordinator.get_phantom_state(self._button)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_press_phantom(self._button, ButtonState.ON, System.NONE)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_press_phantom(self._button, ButtonState.OFF, System.NONE)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
```

---

## `button.py` — ALL ON / ALL OFF (Buttons 16, 17)

Stateless press actions. No feedback — just fires the command.

```python
class RadioRASystemButton(CoordinatorEntity[RadioRACoordinator], ButtonEntity):
    def __init__(self, coordinator, controller_id, button_num, name):
        super().__init__(coordinator)
        self._button = button_num
        slug = "all_on" if button_num == 16 else "all_off"
        self._attr_has_entity_name = True
        self._attr_name = None
        self._attr_unique_id = f"radiora_classic.{controller_id}.button.{slug}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}.button.{slug}")},
            name=name, manufacturer="Lutron", model="RadioRA Classic System Button",
        )

    async def async_press(self) -> None:
        state = ButtonState.ON if self._button == 16 else ButtonState.OFF
        await self.coordinator.async_press_phantom(self._button, state, System.NONE)
```

Always 2 entities created (not user-configurable).

---

## `event.py` — Master Control Buttons

Fires a `press` event when an MBP message is received. No stale state — events are stateless.

```python
class RadioRAMasterEvent(CoordinatorEntity[RadioRACoordinator], EventEntity):
    _attr_event_types = ["press"]

    def __init__(self, coordinator: RadioRACoordinator, controller_id: str, mc_config: dict) -> None:
        super().__init__(coordinator)
        self._master = mc_config["master_control"]
        self._button = mc_config["button"]
        self._attr_has_entity_name = True
        self._attr_name = None
        self._attr_unique_id = f"radiora_classic.{controller_id}.master.mc{self._master}.b{self._button}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}.master.mc{self._master}.b{self._button}")},
            name=mc_config["name"], manufacturer="Lutron", model="RadioRA Classic Master Control",
        )
        if mc_config.get("area"):
            self._attr_device_info["suggested_area"] = mc_config["area"]
        self._last_seen_ts: datetime | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Check if this master button was just pressed and fire event.
        
        Uses timestamp comparison (not time-window) to guarantee exactly-once
        delivery without race conditions from poll timing.
        """
        ts = self.coordinator.get_master_last_press(self._master, self._button)
        if ts is not None and ts != self._last_seen_ts:
            self._last_seen_ts = ts
            self._trigger_event("press")
            self.async_write_ha_state()
```

---

## `sensor.py` — Connection Health (Diagnostic)

```python
class RadioRAConnectionSensor(CoordinatorEntity[RadioRACoordinator], SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, controller_id):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = None
        self._attr_unique_id = f"radiora_classic.{controller_id}.sensor.connection"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}.controller")},
            name=f"RadioRA Classic ({controller_id})",
            manufacturer="Lutron", model="RA-RS232",
        )

    @property
    def native_value(self) -> str:
        return "connected" if self.coordinator.connected else "disconnected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"reconnect_count": self.coordinator.reconnect_count, "url": self.coordinator.url}
```

---

## Platform Summary

| File | Entity Class | Count | Source |
|------|-------------|-------|--------|
| `light.py` | `RadioRALight` | 1 per configured zone | `entry.options["zones"]` |
| `switch.py` | `RadioRAPhantomSwitch` | 1 per phantom button | `entry.options["phantom_buttons"]` |
| `button.py` | `RadioRASystemButton` | Always 2 (ALL ON + ALL OFF) | Hardcoded |
| `event.py` | `RadioRAMasterEvent` | 1 per master control | `entry.options["master_controls"]` |
| `sensor.py` | `RadioRAConnectionSensor` | Always 1 per controller | Hardcoded |

---
