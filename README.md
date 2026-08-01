# Cyborg

An emulator-first host app for the [Brilliant Labs Halo](https://brilliant.xyz)
smart glasses.

Halo is a Bluetooth LE peripheral running an on-device Lua 5.3 VM. A Python host
drives the logic over BLE. This repo ships an emulator so the whole loop can be
built and tested with no hardware attached.

## Quickstart

```bash
uv sync --extra tests
uv run pytest -q
uv run python run_emulator.py
```

The last command boots the emulated device, uploads and starts `app/main.lua`,
sends it a few messages, and writes `framebuffer.png`.

## Notification mirror

The first real app. The host follows a source, keeps a rolling window of recent
notifications, and pushes a prepared screen to the glasses.

```bash
uv run python run_notify.py                           # scripted demo
uv run python run_notify.py --file /var/log/syslog --duration 20
uv run python run_notify.py --command "journalctl -f -n0"
```

Notifications wrap to the display width, carry a relative age label, expire
after `--ttl` seconds, and scroll oldest-first once the screen is full. All of
that happens host-side; `app/notify.lua` only draws what it is handed.

Arrivals and expiries are pushed to the glasses immediately. Age labels would
otherwise force a redraw every second, so they are refreshed at most once per
`--refresh` seconds (default 5, `0` to freeze them until something real
happens).

## Layout

| Path | What it is |
|---|---|
| `app/main.lua` | Minimal echo app, used by the smoke tests |
| `app/notify.lua` | Notification mirror renderer |
| `src/halo_host/` | Host-side driver: app lifecycle, messaging, notifications |
| `src/halo_emulator/` | Experimental emulator: Lua VM, display, BLE stand-in |
| `tests/` | End-to-end and unit tests |

## Status

Early. The emulator is a development aid, not a hardware model, and parts of the
API surface are unverified placeholders inherited from Brilliant's earlier Frame
device. See [CLAUDE.md](CLAUDE.md) before renaming anything.
