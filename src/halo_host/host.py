"""The host side of the Halo link.

`HaloHost` knows how to push a Lua app onto the device, start it, and exchange
messages with it. It talks to a transport -- anything with `.connect()`,
`.send(bytes)` and `.on_receive(handler)` -- so swapping the emulator for a real
BLE central later does not touch this file.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from halo_host import brilliant_msg as msg

DEFAULT_APP = Path(__file__).resolve().parents[2] / "app" / "main.lua"


class HaloHost:
    """Drives an attached Halo device (emulated or, later, real)."""

    def __init__(self, transport) -> None:
        self.transport = transport
        self._reassembler = msg.Reassembler()
        self.prints: list[str] = []
        self.acks: list[bytes] = []
        self.app_data: list[str] = []
        self._on_app_data: Callable[[str], None] | None = None

    # -- link management ---------------------------------------------------

    def connect(self) -> None:
        self.transport.connect()

    def disconnect(self) -> None:
        self.transport.disconnect()

    def handle_fragment(self, fragment: bytes) -> None:
        """Consume one transport fragment arriving from the device."""
        for msg_type, payload in self._reassembler.feed(fragment):
            if msg_type == msg.MSG_PRINT:
                self.prints.append(payload.decode("utf-8"))
            elif msg_type == msg.MSG_ACK:
                self.acks.append(payload)
            elif msg_type == msg.MSG_APP_DATA:
                text = payload.decode("utf-8")
                self.app_data.append(text)
                if self._on_app_data is not None:
                    self._on_app_data(text)
            else:
                raise msg.ProtocolError(
                    f"host received unknown message type 0x{msg_type:02x}"
                )

    def on_app_data(self, handler: Callable[[str], None]) -> None:
        """Register a callback for payloads the on-device app sends up."""
        self._on_app_data = handler

    # -- app lifecycle -----------------------------------------------------

    def upload_app(self, path: str | Path = DEFAULT_APP, name: str = "main.lua") -> str:
        """Read a Lua file from disk and write it to the device."""
        source = Path(path).read_text(encoding="utf-8")
        # Placeholder name -- see brilliant_msg's module docstring before renaming.
        msg.upload_frame_app(self.transport.send, source, name=name)
        return source

    def start_app(self, name: str = "main.lua") -> None:
        # Placeholder name -- see brilliant_msg's module docstring before renaming.
        msg.start_frame_app(self.transport.send, name=name)

    def run_lua(self, source: str) -> None:
        """Evaluate a Lua snippet on the device without touching its filesystem."""
        self.transport.send(msg.encode(msg.MSG_LUA, source.encode("utf-8")))

    def send_data(self, text: str) -> None:
        """Deliver a payload to the running app's receive callback."""
        self.transport.send(msg.encode(msg.MSG_DATA, text.encode("utf-8")))


def connect_emulator(display=None):
    """Build a host wired to a fresh emulated device.

    Returns `(host, device)`. Two one-way transports are used so that each
    direction fragments independently, the way two GATT characteristics would.
    """
    from halo_emulator.device import EmulatedHalo
    from halo_emulator.transport import LoopbackTransport

    host_to_device = LoopbackTransport()
    device_to_host = LoopbackTransport()

    host = HaloHost(host_to_device)
    device = EmulatedHalo(device_to_host.send, display=display)

    host_to_device.on_receive(device.handle_fragment)
    device_to_host.on_receive(host.handle_fragment)

    host_to_device.connect()
    device_to_host.connect()
    return host, device
