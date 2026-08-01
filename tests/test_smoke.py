"""Smoke tests for the emulator baseline.

These assert that the whole loop works end to end: a Lua app is uploaded over
the framed link, runs on a real Lua 5.3 VM, draws into the framebuffer, and
talks back to the host. They deliberately do not pin down the *content* of the
display beyond "something was drawn", because the layout is expected to churn.
"""

from __future__ import annotations

import struct

import pytest

from halo_emulator.device import EmulatedHalo, LuaAppError
from halo_emulator.display import Display
from halo_emulator.transport import LoopbackTransport, TransportClosed
from halo_host import brilliant_msg as msg
from halo_host import connect_emulator


@pytest.fixture
def wired():
    host, device = connect_emulator()
    return host, device


# -- framing -----------------------------------------------------------------


def test_encode_roundtrips_through_reassembler():
    frame = msg.encode(msg.MSG_DATA, b"payload")
    assert list(msg.Reassembler().feed(frame)) == [(msg.MSG_DATA, b"payload")]


def test_reassembler_joins_messages_split_across_fragments():
    frame = msg.encode(msg.MSG_DATA, b"x" * 500)
    r = msg.Reassembler()
    # Feed it one byte at a time; nothing should emerge until the last byte.
    out = []
    for i in range(len(frame)):
        out.extend(r.feed(frame[i : i + 1]))
    assert out == [(msg.MSG_DATA, b"x" * 500)]


def test_reassembler_splits_multiple_messages_in_one_fragment():
    blob = msg.encode(msg.MSG_ACK, b"a") + msg.encode(msg.MSG_PRINT, b"b")
    assert list(msg.Reassembler().feed(blob)) == [
        (msg.MSG_ACK, b"a"),
        (msg.MSG_PRINT, b"b"),
    ]


def test_encode_rejects_oversized_payload():
    with pytest.raises(msg.ProtocolError):
        msg.encode(msg.MSG_DATA, b"\0" * (msg.MAX_PAYLOAD + 1))


# -- transport ---------------------------------------------------------------


def test_transport_fragments_to_mtu():
    t = LoopbackTransport(mtu=16)
    t.on_receive(lambda _: None)
    t.connect()
    t.send(b"z" * 40)
    assert [len(f) for f in t.sent_fragments] == [16, 16, 8]


def test_send_on_closed_transport_raises():
    t = LoopbackTransport()
    t.on_receive(lambda _: None)
    with pytest.raises(TransportClosed):
        t.send(b"nope")


# -- device ------------------------------------------------------------------


def test_device_runs_lua_53():
    device = EmulatedHalo(send=lambda _: None)
    assert device.lua.eval("_VERSION") == "Lua 5.3"


def test_starting_missing_file_raises():
    device = EmulatedHalo(send=lambda _: None)
    with pytest.raises(LuaAppError):
        device._run_file("absent.lua")


def test_sleep_advances_virtual_clock_without_blocking(wired):
    host, device = wired
    host.run_lua("frame.sleep(2.5)")
    assert device.clock == pytest.approx(2.5)


# -- end to end --------------------------------------------------------------


def test_upload_and_start_app(wired):
    host, device = wired
    source = host.upload_app()

    assert "main.lua" in device.files
    assert device.files["main.lua"] == source

    host.start_app()
    assert device.running_app == "main.lua"
    assert any("Lua 5.3" in line for line in host.prints)


def test_app_draws_something(wired):
    host, device = wired
    host.upload_app()
    assert device.display.is_blank()

    host.start_app()
    assert not device.display.is_blank()
    assert device.display.show_count >= 1


def test_app_echoes_host_messages(wired):
    host, device = wired
    host.upload_app()
    host.start_app()

    before = device.display.checksum()
    host.send_data("ping")

    assert "ok:4" in host.app_data
    assert device.display.checksum() != before, "display should change on new data"


def test_app_data_callback_fires(wired):
    host, device = wired
    received: list[str] = []
    host.on_app_data(received.append)

    host.upload_app()
    host.start_app()
    host.send_data("hi")

    assert received[0] == "ready"
    assert "ok:2" in received


def test_unknown_message_type_is_rejected(wired):
    host, device = wired
    with pytest.raises(msg.ProtocolError):
        device.handle_fragment(msg.encode(0x7F, b""))


# -- rendering ---------------------------------------------------------------


def test_to_png_writes_a_valid_png(tmp_path, wired):
    host, device = wired
    host.upload_app()
    host.start_app()

    path = device.display.to_png(tmp_path / "out.png")
    data = path.read_bytes()

    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    # IHDR payload starts at byte 16: width, height, then bit depth and colour type.
    width, height, depth, colour = struct.unpack(">2I2B", data[16:26])
    assert (width, height) == (device.display.width, device.display.height)
    assert (depth, colour) == (8, 2), "expected 8-bit RGB"


def test_text_is_clipped_not_crashing():
    d = Display(width=32, height=16)
    d.text("this runs well past the right edge", 20, 10)
    d.show()
    assert not d.is_blank()


def test_show_is_required_before_output_is_visible():
    d = Display(width=16, height=16)
    d.text("A", 0, 0)
    assert d.is_blank(), "drawing should only touch the back buffer"
    d.show()
    assert not d.is_blank()
