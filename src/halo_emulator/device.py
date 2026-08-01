"""The emulated Halo peripheral: a Lua 5.3 VM plus a display and a BLE link.

The device owns a real Lua interpreter (lupa's bundled Lua 5.3, matching the
VM described for the hardware), a tiny in-memory filesystem, and a framebuffer.
The host talks to it only through framed messages, so host code written against
this emulator is not coupled to the emulator's internals.
"""

from __future__ import annotations

from collections.abc import Callable

from lupa.lua53 import LuaRuntime

from halo_emulator.display import Display
from halo_host import brilliant_msg as msg


class LuaAppError(RuntimeError):
    """Raised when the on-device Lua app fails to load or run."""


class EmulatedHalo:
    """An in-process stand-in for the glasses.

    Parameters
    ----------
    send:
        Callable used to push bytes back to the host (the device -> host
        direction of the link).
    display:
        Framebuffer to render into. A default-sized one is created if omitted.
    """

    def __init__(
        self, send: Callable[[bytes], None], display: Display | None = None
    ) -> None:
        self._send = send
        self.display = display or Display()
        self.files: dict[str, str] = {}
        self.printed: list[str] = []
        self.running_app: str | None = None
        # Virtual clock in seconds. frame.sleep advances this instead of
        # blocking, which keeps the test suite fast and deterministic.
        self.clock = 0.0

        self._reassembler = msg.Reassembler()
        self._data_callback = None
        self.lua = LuaRuntime(encoding="utf-8", unpack_returned_tuples=True)
        self._install_lua_api()

    # -- Lua-facing API ----------------------------------------------------

    def _install_lua_api(self) -> None:
        """Expose the `frame` global to Lua.

        NAMING WARNING: the `frame.*` surface below is a Frame-era placeholder
        and is NOT verified against the Halo Lua SDK. It is defined here in one
        place precisely so it can be corrected in one place once the real names
        are known. Do not rename piecemeal. See CLAUDE.md.
        """
        lua = self.lua

        display_tbl = lua.table_from(
            {
                "clear": self._lua_display_clear,
                "text": self._lua_display_text,
                "show": self._lua_display_show,
                "width": self.display.width,
                "height": self.display.height,
            }
        )
        bluetooth_tbl = lua.table_from(
            {
                "send": self._lua_bluetooth_send,
                "receive_callback": self._lua_receive_callback,
                "max_length": lambda: msg.MAX_PAYLOAD,
            }
        )
        frame_tbl = lua.table_from(
            {
                "display": display_tbl,
                "bluetooth": bluetooth_tbl,
                "sleep": self._lua_sleep,
                "time": lua.table_from({"utc": lambda: self.clock}),
            }
        )
        lua.globals()["frame"] = frame_tbl
        # Route Lua print() to the host so app-side logging is observable.
        lua.globals()["print"] = self._lua_print

    def _lua_display_clear(self) -> None:
        self.display.clear()

    def _lua_display_text(self, s, x, y, scale=1) -> None:
        self.display.text(str(s), int(x), int(y), scale=int(scale))

    def _lua_display_show(self) -> None:
        self.display.show()

    def _lua_bluetooth_send(self, data) -> None:
        payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        self._send(msg.encode(msg.MSG_APP_DATA, payload))

    def _lua_receive_callback(self, fn) -> None:
        self._data_callback = fn

    def _lua_sleep(self, seconds) -> None:
        self.clock += float(seconds)

    def _lua_print(self, *args) -> None:
        line = "\t".join(str(a) for a in args)
        self.printed.append(line)
        self._send(msg.encode(msg.MSG_PRINT, line.encode("utf-8")))

    # -- host-facing API ---------------------------------------------------

    def handle_fragment(self, fragment: bytes) -> None:
        """Consume one transport fragment from the host."""
        for msg_type, payload in self._reassembler.feed(fragment):
            self._dispatch(msg_type, payload)

    def _dispatch(self, msg_type: int, payload: bytes) -> None:
        if msg_type == msg.MSG_FILE_WRITE:
            name, _, source = payload.partition(b"\0")
            self.files[name.decode("utf-8")] = source.decode("utf-8")
            self._send(msg.encode(msg.MSG_ACK, name))
        elif msg_type == msg.MSG_APP_START:
            name = payload.decode("utf-8")
            self._run_file(name)
            self._send(msg.encode(msg.MSG_ACK, payload))
        elif msg_type == msg.MSG_LUA:
            self._eval(payload.decode("utf-8"))
            self._send(msg.encode(msg.MSG_ACK, b""))
        elif msg_type == msg.MSG_DATA:
            self._deliver_to_app(payload)
        else:
            raise msg.ProtocolError(f"device received unknown message type 0x{msg_type:02x}")

    def _run_file(self, name: str) -> None:
        if name not in self.files:
            raise LuaAppError(f"no such file on device: {name!r}")
        self._eval(self.files[name])
        self.running_app = name

    def _eval(self, source: str):
        try:
            return self.lua.execute(source)
        except Exception as exc:  # lupa raises LuaError/LuaSyntaxError
            raise LuaAppError(f"Lua execution failed: {exc}") from exc

    def _deliver_to_app(self, payload: bytes) -> None:
        if self._data_callback is None:
            return  # no app has registered interest; drop, as the device would
        try:
            self._data_callback(payload.decode("utf-8"))
        except Exception as exc:
            raise LuaAppError(f"Lua receive callback failed: {exc}") from exc
