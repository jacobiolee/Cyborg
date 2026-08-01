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

## Layout

| Path | What it is |
|---|---|
| `app/main.lua` | The Lua app that runs on the glasses |
| `src/halo_host/` | Host-side driver: app lifecycle and messaging |
| `src/halo_emulator/` | Experimental emulator: Lua VM, display, BLE stand-in |
| `tests/test_smoke.py` | End-to-end smoke tests |

## Status

Early. The emulator is a development aid, not a hardware model, and parts of the
API surface are unverified placeholders inherited from Brilliant's earlier Frame
device. See [CLAUDE.md](CLAUDE.md) before renaming anything.
