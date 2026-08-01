"""A stand-in for the BLE link between the Python host and the glasses.

The real device is a BLE peripheral and the host is the central. Rather than
model GATT, this transport models the two properties that actually shape host
code: messages arrive as MTU-sized fragments, and delivery is asynchronous with
respect to the caller. Everything runs in-process, single-threaded.
"""

from __future__ import annotations

from collections.abc import Callable

# Nordic UART-style payload budget: 247-byte ATT MTU minus 3 bytes of ATT
# header. Unverified against Halo, but it is the number that makes host-side
# chunking bugs show up in the emulator instead of on hardware.
DEFAULT_MTU = 244


class TransportClosed(RuntimeError):
    """Raised when writing to a transport that is not connected."""


class LoopbackTransport:
    """Wires a host directly to an emulated device.

    `send` fragments the payload to `mtu` and hands each fragment to the peer's
    receive handler immediately. Fragments are reassembled by the framing layer
    in halo_host.brilliant_msg, not here -- the transport is deliberately dumb.
    """

    def __init__(self, mtu: int = DEFAULT_MTU) -> None:
        self.mtu = mtu
        self.connected = False
        self._peer_handler: Callable[[bytes], None] | None = None
        self.sent_fragments: list[bytes] = []

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def on_receive(self, handler: Callable[[bytes], None]) -> None:
        """Register the callback invoked for each fragment arriving from us."""
        self._peer_handler = handler

    def send(self, payload: bytes) -> None:
        if not self.connected:
            raise TransportClosed("transport is not connected")
        if self._peer_handler is None:
            raise TransportClosed("no peer is attached to this transport")
        for start in range(0, len(payload), self.mtu):
            fragment = payload[start : start + self.mtu]
            self.sent_fragments.append(fragment)
            self._peer_handler(fragment)
