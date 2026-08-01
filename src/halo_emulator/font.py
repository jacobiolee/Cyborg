"""A 5x7 bitmap font, embedded so the emulator has zero asset dependencies.

Each printable ASCII character (0x20..0x7E) maps to five column bytes. Within a
column, bit 0 is the top row and bit 6 is the bottom row. This is the classic
5x7 GLCD layout; it is used only for emulator rendering and says nothing about
what the real device's text rendering looks like.
"""

GLYPH_WIDTH = 5
GLYPH_HEIGHT = 7
# One space column is added between glyphs when drawing a string.
ADVANCE = GLYPH_WIDTH + 1

_FONT_HEX = (
    "0000000000"  # (space)
    "00005f0000"  # !
    "0007000700"  # "
    "147f147f14"  # #
    "242a7f2a12"  # $
    "2313086462"  # %
    "3649552250"  # &
    "0005030000"  # '
    "001c224100"  # (
    "0041221c00"  # )
    "14083e0814"  # *
    "08083e0808"  # +
    "0050300000"  # ,
    "0808080808"  # -
    "0060600000"  # .
    "2010080402"  # /
    "3e5149453e"  # 0
    "00427f4000"  # 1
    "4261514946"  # 2
    "2141454b31"  # 3
    "1814127f10"  # 4
    "2745454539"  # 5
    "3c4a494930"  # 6
    "0171090503"  # 7
    "3649494936"  # 8
    "064949291e"  # 9
    "0036360000"  # :
    "0056360000"  # ;
    "0008142241"  # <
    "1414141414"  # =
    "4122140800"  # >
    "0201510906"  # ?
    "324979413e"  # @
    "7e1111117e"  # A
    "7f49494936"  # B
    "3e41414122"  # C
    "7f4141221c"  # D
    "7f49494941"  # E
    "7f09090101"  # F
    "3e41415132"  # G
    "7f0808087f"  # H
    "00417f4100"  # I
    "2040413f01"  # J
    "7f08142241"  # K
    "7f40404040"  # L
    "7f0204027f"  # M
    "7f0408107f"  # N
    "3e4141413e"  # O
    "7f09090906"  # P
    "3e4151215e"  # Q
    "7f09192946"  # R
    "4649494931"  # S
    "01017f0101"  # T
    "3f4040403f"  # U
    "1f2040201f"  # V
    "7f2018207f"  # W
    "6314081463"  # X
    "0304780403"  # Y
    "6151494543"  # Z
    "00007f4141"  # [
    "0204081020"  # backslash
    "41417f0000"  # ]
    "0402010204"  # ^
    "4040404040"  # _
    "0001020400"  # `
    "2054545478"  # a
    "7f48444438"  # b
    "3844444420"  # c
    "384444487f"  # d
    "3854545418"  # e
    "087e090102"  # f
    "0c5252523e"  # g
    "7f08040478"  # h
    "00447d4000"  # i
    "2040443d00"  # j
    "7f10284400"  # k
    "00417f4000"  # l
    "7c04180478"  # m
    "7c08040478"  # n
    "3844444438"  # o
    "7c14141408"  # p
    "081414187c"  # q
    "7c08040408"  # r
    "4854545420"  # s
    "043f444020"  # t
    "3c4040207c"  # u
    "1c2040201c"  # v
    "3c4030403c"  # w
    "4428102844"  # x
    "0c5050503c"  # y
    "4464544c44"  # z
    "0008364100"  # {
    "00007f0000"  # |
    "0041360800"  # }
    "08082a1c08"  # ~
)

FIRST_CHAR = 0x20
LAST_CHAR = 0x7E

_FONT = bytes.fromhex(_FONT_HEX)

_EXPECTED = (LAST_CHAR - FIRST_CHAR + 1) * GLYPH_WIDTH
if len(_FONT) != _EXPECTED:  # pragma: no cover - guards a typo in the table above
    raise RuntimeError(f"font table is {len(_FONT)} bytes, expected {_EXPECTED}")


def glyph(ch: str) -> bytes:
    """Return the five column bytes for `ch`, falling back to '?' if unmapped."""
    code = ord(ch)
    if not (FIRST_CHAR <= code <= LAST_CHAR):
        code = ord("?")
    offset = (code - FIRST_CHAR) * GLYPH_WIDTH
    return _FONT[offset : offset + GLYPH_WIDTH]


def text_width(s: str) -> int:
    """Pixel width of `s` as drawn by Display.text (no trailing spacer column)."""
    if not s:
        return 0
    return len(s) * ADVANCE - 1
