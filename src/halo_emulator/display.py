"""An RGB framebuffer with a dependency-free PNG writer.

Geometry and colour depth here are EMULATOR CHOICES, not verified Halo specs.
They are centralised in this module so that swapping them for real values later
is a one-line change. See CLAUDE.md.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path

from halo_emulator import font

# Unverified: chosen to give the host something concrete to draw into.
WIDTH = 640
HEIGHT = 400

RGB = tuple[int, int, int]

BLACK: RGB = (0, 0, 0)
WHITE: RGB = (255, 255, 255)


class Display:
    """A mutable RGB888 framebuffer.

    The device is assumed to double-buffer: drawing calls mutate a back buffer
    and `show()` promotes it to the visible buffer. `to_png` always renders the
    visible buffer, so a half-drawn frame never reaches disk.
    """

    def __init__(self, width: int = WIDTH, height: int = HEIGHT) -> None:
        self.width = width
        self.height = height
        self._back = bytearray(width * height * 3)
        self._front = bytearray(width * height * 3)
        self.show_count = 0

    # -- drawing -----------------------------------------------------------

    def clear(self, color: RGB = BLACK) -> None:
        self._back[:] = bytes(color) * (self.width * self.height)

    def pixel(self, x: int, y: int, color: RGB) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return  # clip silently, as a real display driver would
        offset = (y * self.width + x) * 3
        self._back[offset : offset + 3] = bytes(color)

    def fill_rect(self, x: int, y: int, w: int, h: int, color: RGB) -> None:
        for row in range(y, y + h):
            for col in range(x, x + w):
                self.pixel(col, row, color)

    def text(self, s: str, x: int, y: int, color: RGB = WHITE, scale: int = 1) -> None:
        """Draw `s` with its top-left corner at (x, y)."""
        cursor = x
        for ch in s:
            columns = font.glyph(ch)
            for col_index, bits in enumerate(columns):
                for row in range(font.GLYPH_HEIGHT):
                    if not (bits >> row) & 1:
                        continue
                    px = cursor + col_index * scale
                    py = y + row * scale
                    if scale == 1:
                        self.pixel(px, py, color)
                    else:
                        self.fill_rect(px, py, scale, scale, color)
            cursor += font.ADVANCE * scale

    def show(self) -> None:
        """Promote the back buffer to the visible buffer."""
        self._front[:] = self._back
        self.show_count += 1

    # -- inspection --------------------------------------------------------

    @property
    def visible(self) -> bytes:
        return bytes(self._front)

    def is_blank(self) -> bool:
        return not any(self._front)

    def checksum(self) -> str:
        """Stable digest of the visible buffer, for assertions in tests."""
        return hashlib.sha256(self._front).hexdigest()

    def to_png(self, path: str | Path) -> Path:
        """Write the visible buffer as an 8-bit RGB PNG. No third-party deps."""
        raw = bytearray()
        stride = self.width * 3
        for row in range(self.height):
            raw.append(0)  # per-scanline filter type 0 (None)
            raw += self._front[row * stride : (row + 1) * stride]

        def chunk(tag: bytes, data: bytes) -> bytes:
            body = tag + data
            return struct.pack(">I", len(data)) + body + struct.pack(
                ">I", zlib.crc32(body) & 0xFFFFFFFF
            )

        header = struct.pack(">2I5B", self.width, self.height, 8, 2, 0, 0, 0)
        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b"")
        )

        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(png)
        return out
