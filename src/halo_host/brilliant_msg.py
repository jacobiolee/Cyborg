"""Message framing for the host <-> glasses link.

NAMING WARNING
--------------
`upload_frame_app` and `start_frame_app` are Frame-era placeholder names. They
have NOT been verified against the Halo SDK. Do not rename them to something
that merely looks more Halo-ish -- if they turn out to be wrong, the fix is to
check the Halo Python SDK docs and rename deliberately, in one pass, with the
Lua side updated to match. See CLAUDE.md.

Wire format: every message is

    b'\\xa5' | type: u8 | length: u16 big-endian | payload[length]

The magic byte lets the reassembler resynchronise if a fragment is dropped,
which the loopback transport never does but real BLE will.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

MAGIC = 0xA5
HEADER_LEN = 4
MAX_PAYLOAD = 0xFFFF

# Host -> device
MSG_LUA = 0x01  # execute a Lua source string immediately
MSG_DATA = 0x02  # opaque payload delivered to the running app
MSG_FILE_WRITE = 0x10  # b"name\0contents" -> device filesystem
MSG_APP_START = 0x11  # b"name" -> run that file

# Device -> host
MSG_PRINT = 0x20  # captured Lua print() output
MSG_ACK = 0x21  # acknowledgement of the preceding host message
MSG_APP_DATA = 0x22  # payload sent by the app

TYPE_NAMES = {
    MSG_LUA: "LUA",
    MSG_DATA: "DATA",
    MSG_FILE_WRITE: "FILE_WRITE",
    MSG_APP_START: "APP_START",
    MSG_PRINT: "PRINT",
    MSG_ACK: "ACK",
    MSG_APP_DATA: "APP_DATA",
}


class ProtocolError(RuntimeError):
    """Raised when a malformed frame is decoded."""


def encode(msg_type: int, payload: bytes = b"") -> bytes:
    """Frame `payload` as a single message."""
    if len(payload) > MAX_PAYLOAD:
        raise ProtocolError(
            f"payload of {len(payload)} bytes exceeds the {MAX_PAYLOAD}-byte frame limit"
        )
    return bytes([MAGIC, msg_type]) + len(payload).to_bytes(2, "big") + payload


class Reassembler:
    """Buffers transport fragments and yields complete messages.

    A BLE fragment boundary has nothing to do with a message boundary: one
    message may span several fragments and one fragment may carry several
    messages. Feeding every fragment through here keeps that distinction out of
    the rest of the codebase.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, fragment: bytes) -> Iterator[tuple[int, bytes]]:
        self._buf += fragment
        while True:
            # Resynchronise to the next magic byte if we are mid-garbage.
            start = self._buf.find(MAGIC)
            if start == -1:
                self._buf.clear()
                return
            if start:
                del self._buf[:start]
            if len(self._buf) < HEADER_LEN:
                return
            length = int.from_bytes(self._buf[2:4], "big")
            if len(self._buf) < HEADER_LEN + length:
                return
            msg_type = self._buf[1]
            payload = bytes(self._buf[HEADER_LEN : HEADER_LEN + length])
            del self._buf[: HEADER_LEN + length]
            yield msg_type, payload


# --- Frame-era placeholder API. Names unverified -- see module docstring. -----


def upload_frame_app(
    send: Callable[[bytes], None], source: str, name: str = "main.lua"
) -> None:
    """Write a Lua source file to the device filesystem.

    PLACEHOLDER NAME -- not verified against the Halo SDK.
    """
    payload = name.encode("utf-8") + b"\0" + source.encode("utf-8")
    send(encode(MSG_FILE_WRITE, payload))


def start_frame_app(send: Callable[[bytes], None], name: str = "main.lua") -> None:
    """Run a previously uploaded Lua file.

    PLACEHOLDER NAME -- not verified against the Halo SDK.
    """
    send(encode(MSG_APP_START, name.encode("utf-8")))
