#!/usr/bin/env python3
"""Boot the emulator, run app/main.lua against it, and render the framebuffer.

    uv run python run_emulator.py

Writes framebuffer.png next to this file and prints a summary of the exchange.
"""

from __future__ import annotations

import sys
from pathlib import Path

from halo_host import connect_emulator

OUTPUT = Path(__file__).resolve().parent / "framebuffer.png"

DEMO_MESSAGES = [
    "hello from the host",
    "battery 87%",
    "3 unread",
]


def main() -> int:
    host, device = connect_emulator()

    source = host.upload_app()
    print(f"uploaded app/main.lua ({len(source)} bytes)")

    host.start_app()
    print(f"started {device.running_app} on the emulated device")

    for message in DEMO_MESSAGES:
        host.send_data(message)
    print(f"sent {len(DEMO_MESSAGES)} messages")

    path = device.display.to_png(OUTPUT)

    print()
    print("--- device print() output ---")
    for line in host.prints:
        print(f"  {line}")
    print("--- app -> host payloads ---")
    for line in host.app_data:
        print(f"  {line}")
    print()
    print(f"display     {device.display.width}x{device.display.height}")
    print(f"show() calls {device.display.show_count}")
    print(f"checksum    {device.display.checksum()[:16]}")
    print(f"wrote       {path} ({path.stat().st_size} bytes)")

    if device.display.is_blank():
        print("ERROR: framebuffer is blank", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
