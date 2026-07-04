# Phase 5: Diagnostics, Services, CSV Import/Export

## `diagnostics.py`

Returns redacted config + runtime state for debugging.

```python
TO_REDACT = {"url"}  # Connection URL may contain internal IPs

async def async_get_config_entry_diagnostics(hass, entry) -> dict[str, Any]:
    data = entry.runtime_data
    coordinator = data.coordinator

    return async_redact_data({
        "entry_data": dict(entry.data),
        "entry_options": dict(entry.options),
        "state": {
            "connected": coordinator.connected,
            "reconnect_count": coordinator.reconnect_count,
            "zone_count": len(entry.options.get("zones", [])),
            "phantom_count": len(entry.options.get("phantom_buttons", [])),
            "master_count": len(entry.options.get("master_controls", [])),
            "zone_levels": {
                f"z{z}": coordinator.get_zone_level(z) for z in range(1, 33)
                if coordinator.get_zone_level(z) is not None
            },
            "phantom_states": {
                f"b{b}": coordinator.get_phantom_state(b) for b in range(1, 16)
            },
        },
    }, TO_REDACT)
```

---

## `services.yaml` — Custom Services

### `radiora_classic.send_command`

Raw command pass-through for advanced users / debugging.

```yaml
send_command:
  fields:
    controller_id:
      required: true
      selector:
        text:
    command:
      required: true
      selector:
        text:
      description: "Raw RS-232 command string (e.g., 'SDL,3,75')"
```

### `radiora_classic.export_config`

Exports current device config to CSV (writes to `/config/` + notification).

```yaml
export_config:
  fields:
    controller_id:
      required: true
      selector:
        text:
```

### Service Registration (in `__init__.py`)

```python
def _get_coordinator(hass: HomeAssistant, controller_id: str) -> RadioRACoordinator:
    """Find coordinator by controller_id across all config entries."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.runtime_data and entry.runtime_data.controller_id == controller_id:
            return entry.runtime_data.coordinator
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="controller_not_found",
        translation_placeholders={"controller_id": controller_id},
    )


async def async_send_command(hass: HomeAssistant, service_call: ServiceCall) -> None:
    controller_id = service_call.data["controller_id"]
    command = service_call.data["command"]
    coordinator = _get_coordinator(hass, controller_id)
    await coordinator.async_send_raw(command)

async def async_export_config(hass, service_call):
    controller_id = service_call.data["controller_id"]
    entry = _get_entry_by_controller(hass, controller_id)
    csv_content = _build_csv_export(entry.options)
    path = hass.config.path(f"radiora_classic_{controller_id}_export.csv")
    await hass.async_add_executor_job(_write_file, path, csv_content)
    hass.components.persistent_notification.async_create(
        f"Config exported to {path}", title="RadioRA Classic Export"
    )
```

---

## CSV Import (Options Flow Step)

Covered in Phase 2 design. Implementation details:

### Parsing Logic

```python
def parse_csv_content(content: str) -> tuple[list[dict], list[str]]:
    """Parse CSV, return (devices, errors).
    
    Returns ALL errors (not just first) for atomic validation.
    """
    errors = []
    devices = []
    
    reader = csv.DictReader(StringIO(content))
    for row_num, row in enumerate(reader, start=2):  # row 1 = header
        device_type = row.get("type", "").strip().lower()
        
        if device_type == "zone":
            zone = _parse_int(row.get("number"), 1, 32)
            if zone is None:
                errors.append(f"Row {row_num}: invalid zone number")
                continue
            devices.append({
                "type": "zone",
                "zone": zone,
                "name": row.get("name", "").strip() or f"Zone {zone}",
                "mode": row.get("mode", "dimmer").strip().lower(),
                "area": row.get("area", "").strip() or None,
                "system": _parse_int(row.get("system"), 1, 2),  # None if empty/invalid
                "fade_sec": _parse_int(row.get("fade_sec"), 0, 240),
            })
        elif device_type == "phantom":
            button = _parse_int(row.get("number"), 1, 15)
            if button is None:
                errors.append(f"Row {row_num}: invalid button number (1-15)")
                continue
            devices.append({
                "type": "phantom",
                "button": button,
                "name": row.get("name", "").strip() or f"Button {button}",
                "area": row.get("area", "").strip() or None,
            })
        elif device_type == "master":
            # Format: "mc:btn" e.g. "1:3"
            parts = row.get("number", "").split(":")
            if len(parts) != 2:
                errors.append(f"Row {row_num}: master format must be 'mc:button'")
                continue
            devices.append({
                "type": "master",
                "master_control": int(parts[0]),
                "button": int(parts[1]),
                "name": row.get("name", "").strip(),
                "area": row.get("area", "").strip() or None,
            })
        else:
            errors.append(f"Row {row_num}: unknown type '{device_type}'")

    return devices, errors
```

### Export Logic

```python
def build_csv_export(options: dict) -> str:
    """Build CSV string from current config options."""
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["type", "number", "name", "mode", "area", "system", "fade_sec"])

    for zone in options.get("zones", []):
        writer.writerow([
            "zone", zone["zone"], zone["name"],
            zone.get("mode", "dimmer"), zone.get("area", ""),
            zone.get("system", ""), zone.get("fade_sec") or "",
        ])
    for btn in options.get("phantom_buttons", []):
        writer.writerow([
            "phantom", btn["button"], btn["name"],
            "", btn.get("area", ""), "", "",
        ])
    for mc in options.get("master_controls", []):
        writer.writerow([
            "master", f"{mc['master_control']}:{mc['button']}",
            mc["name"], "", mc.get("area", ""), "", "",
        ])

    return output.getvalue()
```

---

## Summary

| File | Purpose |
|------|---------|
| `diagnostics.py` | Redacted config + runtime state dump |
| `services.yaml` | Service definitions (send_command, export_config) |
| `__init__.py` | Service handlers registered in `async_setup` |
| `config_flow.py` | CSV import parsing (options flow step) |
