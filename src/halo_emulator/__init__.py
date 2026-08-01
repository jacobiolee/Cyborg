"""Experimental in-process emulator for the Halo smart glasses.

This package exists so the host app can be built and tested with no hardware
attached. It is NOT a faithful hardware model: the display geometry, the BLE
framing, and the Lua API surface are all approximations chosen to make the host
side developable. See CLAUDE.md before treating anything here as spec.
"""

from halo_emulator.device import EmulatedHalo
from halo_emulator.display import Display
from halo_emulator.transport import LoopbackTransport

__all__ = ["EmulatedHalo", "Display", "LoopbackTransport"]
