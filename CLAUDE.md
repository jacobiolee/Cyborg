# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this project is

Cyborg is an **emulator-first host app** for the Brilliant Labs Halo smart
glasses.

The hardware model: Halo is a **Bluetooth LE peripheral** running an **on-device
Lua 5.3 VM**. A **Python host** (phone/laptop) is the BLE central and drives all
the logic; the glasses mostly render and report. The emulator exists so the host
app can be built and tested with **no hardware attached**.

## Read this before changing names

### The code you are reading was written from scratch, not ported

There was no pre-existing baseline. Every file here was authored in this repo
without access to Halo hardware or the Halo SDK. Treat the whole API surface as
a working hypothesis, not as something that was ever validated against a device.

### Frame-era placeholders — do NOT "correct" these

Several identifiers are carried over from Brilliant's earlier **Frame** device.
They are **not verified against the Halo docs**. They may be right, may be
renamed, may not exist on Halo at all.

**Do not rename them because they look wrong.** A plausible-looking rename that
is also wrong is worse than a known-suspect name, because it destroys the signal
that this area is unverified.

Specifically:

| Where | Identifier | Status |
|---|---|---|
| `src/halo_host/brilliant_msg.py` | `upload_frame_app` | Frame-era, unverified |
| `src/halo_host/brilliant_msg.py` | `start_frame_app` | Frame-era, unverified |
| `app/main.lua` | `frame.display.clear/text/show` | Frame-era, unverified |
| `app/main.lua` | `frame.bluetooth.send/receive_callback` | Frame-era, unverified |
| `app/main.lua` | `frame.sleep`, `frame.time.utc` | Frame-era, unverified |

The `frame.*` table is defined in exactly one place —
`EmulatedHalo._install_lua_api` in `src/halo_emulator/device.py` — so that if the
real names turn out to differ, the Lua side and the emulator side can be
corrected together in a single deliberate pass.

**When in doubt, check the docs:**

- Lua SDK: <https://docs.brilliant.xyz/halo/halo-sdk-lua>
- Python SDK: <https://docs.brilliant.xyz/halo/halo-sdk-python>

**or flag it for the user.** Do not guess.

> Operational note: `docs.brilliant.xyz` was **not reachable** from the sandbox
> these files were written in — the egress proxy rejects it with
> `CONNECT tunnel failed, response 403`. If you hit the same wall, say so and
> ask the user rather than substituting a guess.

### `halo_emulator` is experimental

The `halo_emulator` package is **not** a faithful hardware model. These are
emulator conveniences, chosen to make host code developable — none is a verified
Halo spec:

- **640x400 RGB888 display** (`display.py`). Geometry is a guess, centralised at
  the top of the module.
- **244-byte MTU** (`transport.py`). Nordic-UART-shaped (247 ATT MTU − 3). Its
  job is to make host-side chunking bugs surface in tests.
- **Custom wire format** (`brilliant_msg.py`): `0xA5 | type | u16 length |
  payload`. Ours, not Brilliant's.
- **Virtual clock**: `frame.sleep` advances `device.clock` instead of blocking,
  which keeps the suite fast and deterministic. Real sleep behaviour will differ.
- **Synchronous delivery**: `LoopbackTransport.send` invokes the peer's handler
  inline. Real BLE is asynchronous and reorders nothing but delays plenty.

Do not port emulator numbers into hardware-facing code as if they were spec.

## Layout

```
app/main.lua              Lua app that runs on the glasses
run_emulator.py           Boot emulator, run the app, write framebuffer.png
src/halo_host/
  host.py                 HaloHost: upload/start app, exchange messages
  brilliant_msg.py        Framing + the Frame-era placeholder helpers
src/halo_emulator/        EXPERIMENTAL — see above
  device.py               Lua 5.3 VM, filesystem, message dispatch
  display.py              RGB framebuffer + dependency-free PNG writer
  transport.py            BLE stand-in with MTU fragmentation
  font.py                 Embedded 5x7 bitmap font
tests/test_smoke.py       End-to-end smoke tests
```

## Commands

```bash
uv sync --extra tests        # install (creates .venv)
uv run pytest -q             # test suite
uv run python run_emulator.py  # render framebuffer.png
```

## Conventions

- **Lua 5.3 specifically.** `device.py` imports `from lupa.lua53 import
  LuaRuntime`. lupa bundles 5.1–5.5 and defaults to **5.5**; the explicit
  `lua53` import is what matches the device VM. Don't relax it to plain
  `import lupa`.
- **The host talks to a transport, never to the emulator.** `HaloHost` only
  needs `.connect()`, `.send(bytes)`, `.on_receive(handler)`. Keep it that way
  so a real BLE central can be dropped in without touching `host.py`.
- **Fragment boundaries are not message boundaries.** Always feed bytes through
  `brilliant_msg.Reassembler`; never parse a fragment directly.
- **Draw, then `show()`.** Drawing mutates a back buffer; `show()` promotes it.
  `to_png` renders the visible buffer, so a partial frame never reaches disk.
- **No third-party runtime deps beyond lupa.** The PNG writer and font are
  hand-rolled to keep the emulator installable anywhere. Don't add Pillow.
- `framebuffer.png` is generated output and is gitignored.

## Testing

`tests/test_smoke.py` asserts the full loop: upload over the framed link → run
on a real Lua 5.3 VM → draw → talk back. Display assertions deliberately check
"something was drawn" and "the checksum changed", **not** exact pixels — the
layout is expected to churn, and pinning it would make every visual tweak a test
failure.
