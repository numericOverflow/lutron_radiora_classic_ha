# Lutron RadioRA Classic (HACS Integration)

[![Validate](https://github.com/numericOverflow/lutron_radiora_classic_ha/actions/workflows/validate.yml/badge.svg)](https://github.com/numericOverflow/lutron_radiora_classic_ha/actions/workflows/validate.yml)

Home Assistant HACS integration for **Lutron RadioRA Classic** (v1) lighting control via RS-232.

## Features

- **Light entities** — Dimmer zones (brightness control) and on/off-only zones
- **Switch entities** — Phantom buttons (1-15) with LED state feedback
- **Button entities** — ALL ON / ALL OFF system commands
- **Event entities** — Master control button press detection
- **Diagnostic sensor** — Connection health monitoring
- **Push + Poll hybrid** — Real-time LZC/MBP monitoring with periodic ZMPI reconciliation
- **Auto-discovery** — ZMPI zone scanning during setup
- **CSV import/export** — Bulk device configuration
- **Multiple controllers** — Support for multiple RA-RS232 interfaces

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Install "Lutron RadioRA Classic"
3. Restart Home Assistant
4. Go to Settings → Devices & Services → Add Integration → "Lutron RadioRA Classic"

### Manual

Copy `custom_components/radiora_classic/` to your HA `custom_components/` directory.

## Configuration

### Connection URL Formats

| Format | Example | Use Case |
|--------|---------|----------|
| Raw TCP | `socket://192.168.1.50:4999` | ser2net, USR-TCP232 |
| RFC 2217 | `rfc2217://192.168.1.50:4999` | Telnet serial servers |
| Local serial | `/dev/ttyUSB0` | Direct USB-RS232 adapter |

### Setup Flow

1. Enter controller name and connection URL
2. Integration discovers assigned zones via ZMPI
3. Name and configure each zone (dimmer/on-off, area, fade time)
4. Add phantom buttons and master controls via Options

### Options Flow

- **Manage Zones** — Add/Edit/Remove zone configurations
- **Manage Phantom Buttons** — Add/Edit/Remove phantom button scenes
- **Manage Master Controls** — Add/Edit/Remove master control button events
- **Controller Settings** — Poll interval adjustment
- **Import/Export CSV** — Bulk configuration management
- **Re-discover Zones** — Scan for newly assigned zones

## Services

### `radiora_classic.send_command`

Send a raw RS-232 command for advanced/debug use.

### `radiora_classic.export_config`

Export device configuration to a CSV file in `/config/`.

## Bridged Mode (Chronos System Bridge)

For systems using a Chronos Bridge connecting two RadioRA systems, enable "Bridged" during setup. Zones will be tagged with System 1 or System 2.
