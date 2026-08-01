#!/usr/bin/env python3
"""Run the notification mirror against the emulator.

    uv run python run_notify.py                          # scripted demo
    uv run python run_notify.py --file /var/log/syslog    # tail a file
    uv run python run_notify.py --command "journalctl -f -n0"

Writes a PNG of the final screen (default: notifications.png). Live sources run
for --duration seconds, polling every --interval.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from halo_host import connect_emulator
from halo_host.notifications import NotificationMirror, PushPolicy
from halo_host.sources import CommandSource, FileTailSource, IterableSource

APP = Path(__file__).resolve().parent / "app" / "notify.lua"

DEMO_LINES = [
    "sshd: accepted publickey for jacob from 10.0.0.14",
    "calendar: standup in 10 minutes",
    "ci: build #1482 passed on main",
    "mail: 3 unread from brilliant-labs",
    "docker: container 'halo-sim' exited with code 0",
    "battery: 87% discharging, about 4h 20m remaining",
    "ci: build #1483 FAILED on claude/halo-emulator-baseline -- pytest exit 1",
    "calendar: standup starting now",
]


def build_source(args):
    if args.file:
        return FileTailSource(args.file, from_start=args.from_start)
    if args.command:
        return CommandSource(args.command)
    return IterableSource(DEMO_LINES, name="demo")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--file", help="tail this file")
    src.add_argument("--command", help="stream stdout of this command")
    parser.add_argument(
        "--from-start",
        action="store_true",
        help="with --file, replay existing content instead of starting at EOF",
    )
    parser.add_argument("--ttl", type=float, default=60.0, help="seconds before a notification expires")
    parser.add_argument("--duration", type=float, default=8.0, help="how long to follow a live source")
    parser.add_argument("--interval", type=float, default=0.5, help="poll interval in seconds")
    parser.add_argument(
        "--refresh",
        type=float,
        default=5.0,
        help="seconds between age-label-only redraws (0 disables them)",
    )
    parser.add_argument("--out", default="notifications.png", help="where to write the PNG")
    args = parser.parse_args(argv)

    host, device = connect_emulator()
    host.upload_app(APP, name="notify.lua")
    host.start_app("notify.lua")
    print(f"started {device.running_app} ({device.display.width}x{device.display.height})")

    source = build_source(args)
    mirror = NotificationMirror(ttl=args.ttl)
    print(f"source: {source.name}  ttl={args.ttl}s  {mirror.profile.columns}x{mirror.profile.rows} chars")

    policy = PushPolicy(refresh=args.refresh)
    live = bool(args.file or args.command)
    if live:
        _follow(host, mirror, policy, source, args)
    else:
        _demo(host, mirror, policy, source)

    path = device.display.to_png(args.out)

    print()
    print(
        f"pushes      {policy.pushes} "
        f"({policy.content_pushes} content, {policy.refresh_pushes} age-refresh)"
    )
    print(f"notifications {len(mirror)} live / {mirror.total_seen} seen")
    print(f"show() calls {device.display.show_count}")
    print(f"acks        {host.app_data[-1] if host.app_data else '(none)'}")
    print(f"wrote       {path} ({path.stat().st_size} bytes)")

    if device.display.is_blank():
        print("ERROR: framebuffer is blank", file=sys.stderr)
        return 1
    return 0


def _demo(host, mirror, policy, source) -> None:
    """Replay canned lines on a synthetic clock so output is deterministic."""
    now = 1000.0
    while not source.exhausted:
        for line in source.poll():
            mirror.ingest(line, source=source.name, now=now)
            print(f"  + {line[:60]}")
        screen = policy.decide(mirror, now)
        if screen is not None:
            host.send_data(screen)
        now += 7.0  # age the stack between pushes so the labels vary


def _follow(host, mirror, policy, source, args) -> None:
    """Poll a real source until --duration elapses.

    The policy decides what actually goes out: arrivals and expiries go
    immediately, age labels on a throttle.
    """
    deadline = time.monotonic() + args.duration
    try:
        while time.monotonic() < deadline:
            for line in source.poll():
                mirror.ingest(line, source=source.name)
                print(f"  + {line[:60]}")
            screen = policy.decide(mirror)
            if screen is not None:
                host.send_data(screen)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        close = getattr(source, "close", None)
        if close:
            close()


if __name__ == "__main__":
    raise SystemExit(main())
