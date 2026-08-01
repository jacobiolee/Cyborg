"""Tests for the notification mirror.

The mirror is pure host-side logic, so most of this is unit-level: wrapping,
expiry, ordering, truncation. The end-to-end cases at the bottom check that a
screen actually reaches app/notify.lua and gets drawn.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from halo_host import connect_emulator
from halo_host.notifications import (
    DisplayProfile,
    NotificationMirror,
    PushPolicy,
    format_age,
)
from halo_host.sources import FileTailSource, IterableSource

APP = Path(__file__).resolve().parents[1] / "app" / "notify.lua"

# A deliberately tiny screen so truncation and wrapping are easy to reason about.
TINY = DisplayProfile(width=136, height=200, margin=8, body_top=0, body_bottom=66)


@pytest.fixture
def mirror():
    return NotificationMirror(profile=TINY, ttl=60.0)


def test_tiny_profile_geometry():
    assert TINY.columns == 10
    assert TINY.rows == 3


# -- age labels --------------------------------------------------------------


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, "0s"), (9.9, "9s"), (59, "59s"), (60, "1m"), (3599, "59m"), (3600, "1h"), (86400, "1d")],
)
def test_format_age(seconds, expected):
    assert format_age(seconds) == expected


def test_format_age_clamps_negative():
    assert format_age(-5) == "0s"


# -- ingest ------------------------------------------------------------------


def test_blank_lines_are_ignored(mirror):
    assert mirror.ingest("   ") is None
    assert mirror.ingest("") is None
    assert len(mirror) == 0
    assert mirror.total_seen == 0


def test_ingest_strips_and_counts(mirror):
    note = mirror.ingest("  hello  ", now=0)
    assert note is not None
    assert note.text == "hello"
    assert mirror.total_seen == 1


def test_ingest_many_skips_blanks(mirror):
    notes = mirror.ingest_many(["a", "", "b"], now=0)
    assert [n.text for n in notes] == ["a", "b"]


def test_capacity_evicts_oldest():
    m = NotificationMirror(profile=TINY, ttl=None, capacity=3)
    m.ingest_many(["1", "2", "3", "4"], now=0)
    assert [n.text for n in m] == ["2", "3", "4"]


# -- expiry ------------------------------------------------------------------


def test_expired_notifications_drop_out(mirror):
    mirror.ingest("old", now=0)
    mirror.ingest("new", now=50)

    assert len(mirror.live(now=50)) == 2
    # At t=61 the first is 61s old, past the 60s ttl; the second is 11s old.
    assert [n.text for n in mirror.live(now=61)] == ["new"]


def test_ttl_none_keeps_everything():
    m = NotificationMirror(profile=TINY, ttl=None)
    m.ingest("forever", now=0)
    assert len(m.live(now=10_000)) == 1


def test_prune_reports_removed_count(mirror):
    mirror.ingest_many(["a", "b"], now=0)
    assert mirror.prune(now=1000) == 2
    assert len(mirror) == 0


# -- rendering ---------------------------------------------------------------


def test_body_lines_wrap_to_column_width(mirror):
    mirror.ingest("abcdefghijklmnopqrstuvwxyz", now=0)
    lines = mirror.body_lines(now=0)
    assert len(lines) > 1
    assert all(len(line) <= TINY.columns for line in lines)


def test_wrapped_continuation_is_indented(mirror):
    mirror.ingest("alpha beta gamma delta", now=0)
    lines = mirror.body_lines(now=0)
    assert lines[0].startswith("[0s]")
    assert lines[1].startswith("  ")


def test_body_lines_truncate_to_row_count_keeping_newest(mirror):
    mirror.ingest_many(["one", "two", "three", "four", "five"], now=0)
    lines = mirror.body_lines(now=0)
    assert len(lines) == TINY.rows
    assert "five" in lines[-1], "newest notification must stay visible"
    assert not any("one" in line for line in lines), "oldest should scroll off"


def test_age_label_is_present_and_updates(mirror):
    mirror.ingest("ping", now=0)
    assert mirror.body_lines(now=0)[0].startswith("[0s]")
    assert mirror.body_lines(now=30)[0].startswith("[30s]")


def test_screen_is_header_plus_body(mirror):
    mirror.ingest("hi", now=0)
    lines = mirror.screen(now=0).split("\n")
    assert lines[0] == mirror.header(now=0)
    assert lines[1:] == mirror.body_lines(now=0)


def test_header_counts_live_and_total(mirror):
    mirror.ingest_many(["a", "b"], now=0)
    mirror.ingest("c", now=100)
    # a and b have expired by t=100; total_seen still counts them.
    assert mirror.header(now=100) == "1 live / 3 seen"


def test_empty_screen_is_just_the_header(mirror):
    assert mirror.screen(now=0) == "0 live / 0 seen"


def test_long_unbroken_token_does_not_overflow(mirror):
    mirror.ingest("x" * 100, now=0)
    assert all(len(line) <= TINY.columns for line in mirror.body_lines(now=0))


# -- content key -------------------------------------------------------------


def test_content_key_ignores_age(mirror):
    mirror.ingest("steady", now=0)
    assert mirror.content_key(now=0) == mirror.content_key(now=30)
    # ...even though the rendered screen has changed.
    assert mirror.screen(now=0) != mirror.screen(now=30)


def test_content_key_changes_on_arrival(mirror):
    mirror.ingest("first", now=0)
    before = mirror.content_key(now=0)
    mirror.ingest("second", now=0)
    assert mirror.content_key(now=0) != before


def test_content_key_changes_on_expiry(mirror):
    mirror.ingest("transient", now=0)
    before = mirror.content_key(now=0)
    assert mirror.content_key(now=100) != before


# -- push policy -------------------------------------------------------------


def test_policy_pushes_the_initial_screen(mirror):
    assert PushPolicy(refresh=5).decide(mirror, now=0) is not None


def test_policy_stays_quiet_when_nothing_changed(mirror):
    policy = PushPolicy(refresh=5)
    mirror.ingest("hello", now=0)

    assert policy.decide(mirror, now=0) is not None
    assert policy.decide(mirror, now=1) is None
    assert policy.decide(mirror, now=4.9) is None
    assert policy.content_pushes == 1
    assert policy.refresh_pushes == 0


def test_policy_refreshes_ages_after_the_interval(mirror):
    policy = PushPolicy(refresh=5)
    mirror.ingest("hello", now=0)
    policy.decide(mirror, now=0)

    assert policy.decide(mirror, now=5) is not None
    assert policy.refresh_pushes == 1
    # The refresh resets the clock, so the next one is another 5s out.
    assert policy.decide(mirror, now=8) is None
    assert policy.decide(mirror, now=10) is not None


def test_policy_pushes_arrivals_immediately(mirror):
    policy = PushPolicy(refresh=60)
    mirror.ingest("first", now=0)
    policy.decide(mirror, now=0)

    mirror.ingest("second", now=1)
    assert policy.decide(mirror, now=1) is not None, "arrival must not wait for refresh"
    assert policy.content_pushes == 2
    assert policy.refresh_pushes == 0


def test_policy_pushes_expiry_immediately(mirror):
    policy = PushPolicy(refresh=3600)
    mirror.ingest("transient", now=0)
    policy.decide(mirror, now=0)

    # ttl is 60s, so at t=61 the notification is gone -- a content change.
    assert policy.decide(mirror, now=61) is not None
    assert policy.content_pushes == 2


def test_refresh_zero_disables_age_pushes():
    # ttl=None so that nothing expires: this isolates the label-only case.
    # With a ttl the expiry would be a content change and *should* push.
    m = NotificationMirror(profile=TINY, ttl=None)
    policy = PushPolicy(refresh=0)
    m.ingest("hello", now=0)
    policy.decide(m, now=0)

    assert policy.decide(m, now=10_000) is None
    assert policy.refresh_pushes == 0


def test_policy_does_not_refresh_an_empty_screen(mirror):
    policy = PushPolicy(refresh=1)
    policy.decide(mirror, now=0)  # initial empty screen

    assert policy.decide(mirror, now=100) is None, "nothing on screen can age"
    assert policy.refresh_pushes == 0


def test_policy_cuts_traffic_versus_naive_comparison(mirror):
    """The regression this policy exists to prevent."""
    mirror.ingest("steady", now=0)

    naive = len({mirror.screen(now=t) for t in range(0, 60)})
    policy = PushPolicy(refresh=5)
    throttled = sum(policy.decide(mirror, now=t) is not None for t in range(0, 60))

    assert naive > 50, "age labels really do change every second"
    assert throttled <= 13, f"expected roughly 60/5 pushes, got {throttled}"


# -- sources -----------------------------------------------------------------


def test_iterable_source_yields_in_batches():
    s = IterableSource(["a", "b", "c"], per_poll=2)
    assert s.poll() == ["a", "b"]
    assert s.poll() == ["c"]
    assert s.poll() == []
    assert s.exhausted


def test_file_tail_starts_at_eof(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("already here\n", encoding="utf-8")

    source = FileTailSource(log)
    assert source.poll() == [], "pre-existing content should not replay"

    with log.open("a", encoding="utf-8") as fh:
        fh.write("fresh line\n")
    assert source.poll() == ["fresh line"]


def test_file_tail_from_start_replays(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("first\nsecond\n", encoding="utf-8")
    assert FileTailSource(log, from_start=True).poll() == ["first", "second"]


def test_file_tail_handles_truncation(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("one\ntwo\n", encoding="utf-8")
    source = FileTailSource(log)

    log.write_text("rotated\n", encoding="utf-8")  # shorter than before
    assert source.poll() == ["rotated"]


def test_file_tail_missing_file_is_quiet(tmp_path):
    assert FileTailSource(tmp_path / "nope.log").poll() == []


# -- end to end --------------------------------------------------------------


def test_notify_app_renders_a_screen():
    host, device = connect_emulator()
    host.upload_app(APP, name="notify.lua")
    host.start_app("notify.lua")

    assert device.running_app == "notify.lua"
    assert "notify-ready" in host.app_data
    assert not device.display.is_blank(), "app should draw its empty state"

    before = device.display.checksum()

    mirror = NotificationMirror(ttl=None)
    mirror.ingest_many(["ci: build passed", "mail: 2 unread"], now=0)
    host.send_data(mirror.screen(now=0))

    assert device.display.checksum() != before
    assert "drew:2" in host.app_data


def test_screen_larger_than_mtu_survives_fragmentation():
    host, device = connect_emulator()
    host.upload_app(APP, name="notify.lua")
    host.start_app("notify.lua")

    mirror = NotificationMirror(ttl=None)
    # A full screen of wide lines comfortably exceeds the 244-byte MTU.
    mirror.ingest_many([f"{i:02d} " + "w" * 60 for i in range(12)], now=0)
    screen = mirror.screen(now=0)
    assert len(screen.encode()) > device_mtu(host)

    host.send_data(screen)
    assert f"drew:{len(mirror.body_lines(now=0))}" in host.app_data


def device_mtu(host) -> int:
    return host.transport.mtu


def test_expiry_is_visible_on_device():
    host, device = connect_emulator()
    host.upload_app(APP, name="notify.lua")
    host.start_app("notify.lua")

    mirror = NotificationMirror(ttl=30.0)
    mirror.ingest("transient", now=0)

    host.send_data(mirror.screen(now=0))
    assert "drew:1" in host.app_data

    host.send_data(mirror.screen(now=100))
    assert host.app_data[-1] == "drew:0", "expired notification should vanish"
