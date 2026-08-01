"""Host-side driver for the Halo glasses.

`halo_host` holds the logic that runs on the computer/phone side of the BLE
link. It is written against a transport interface, so the same code drives the
emulator and (eventually) real hardware.
"""

from halo_host.host import HaloHost, connect_emulator

__all__ = ["HaloHost", "connect_emulator"]
