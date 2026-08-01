"""The notification mirror: host-side model of what the glasses should show.

All of the logic lives here rather than in Lua, which matches the hardware
model this project assumes -- the host drives, the glasses render. The device
receives an already-wrapped, already-expired, already-truncated list of lines
and does nothing but draw it.

That split is deliberate. Wrapping needs text metrics, and the alternative was
to invent a `frame.display.text_width` call to do it on-device -- more surface
area on the very API that CLAUDE.md flags as unverified. Keeping the metrics in
`DisplayProfile` here means the guesswork stays on the host, where it is cheap
to correct.
"""

from __future__ import annotations

import textwrap
import time
from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

# Continuation lines of a wrapped notification are indented this far.
WRAP_INDENT = "  "


@dataclass(frozen=True)
class DisplayProfile:
    """Host-side model of the device's text geometry.

    UNVERIFIED. These numbers mirror the emulator's display and font, which are
    themselves guesses (see CLAUDE.md). They are duplicated here rather than
    imported from `halo_emulator` on purpose: the host must not depend on the
    emulator, and against real hardware these would come from config anyway.
    """

    width: int = 640
    height: int = 400
    margin: int = 16
    # Must match halo_emulator.font.ADVANCE (glyph width + 1 spacer column).
    glyph_advance: int = 6
    body_scale: int = 2
    line_spacing: int = 22
    body_top: int = 76
    body_bottom: int = 356

    @property
    def columns(self) -> int:
        """How many characters fit on one body line."""
        usable = self.width - 2 * self.margin
        return max(1, usable // (self.glyph_advance * self.body_scale))

    @property
    def rows(self) -> int:
        """How many body lines fit vertically."""
        usable = self.body_bottom - self.body_top
        return max(1, usable // self.line_spacing)


@dataclass(frozen=True)
class Notification:
    text: str
    source: str = ""
    received_at: float = 0.0

    def age(self, now: float) -> float:
        return max(0.0, now - self.received_at)


def format_age(seconds: float) -> str:
    """Compact age label: 9s, 4m, 2h, 3d."""
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


class NotificationMirror:
    """Holds recent notifications and renders them to a screen payload.

    Parameters
    ----------
    profile:
        Text geometry used for wrapping and truncation.
    ttl:
        Seconds a notification stays visible. `None` disables expiry.
    capacity:
        Hard cap on retained notifications, independent of ttl.
    """

    def __init__(
        self,
        profile: DisplayProfile | None = None,
        ttl: float | None = 60.0,
        capacity: int = 64,
        clock=time.monotonic,
    ) -> None:
        self.profile = profile or DisplayProfile()
        self.ttl = ttl
        self.capacity = capacity
        self._clock = clock
        self._items: deque[Notification] = deque(maxlen=capacity)
        self.total_seen = 0

    # -- ingest ------------------------------------------------------------

    def now(self) -> float:
        return self._clock()

    def ingest(
        self, text: str, *, source: str = "", now: float | None = None
    ) -> Notification | None:
        """Record one notification. Blank lines are ignored and return None."""
        text = text.strip()
        if not text:
            return None
        note = Notification(
            text=text, source=source, received_at=self.now() if now is None else now
        )
        self._items.append(note)
        self.total_seen += 1
        return note

    def ingest_many(
        self, texts: Iterable[str], *, source: str = "", now: float | None = None
    ) -> list[Notification]:
        return [n for t in texts if (n := self.ingest(t, source=source, now=now))]

    # -- state -------------------------------------------------------------

    def prune(self, now: float | None = None) -> int:
        """Drop expired notifications. Returns how many were removed."""
        if self.ttl is None:
            return 0
        now = self.now() if now is None else now
        removed = 0
        while self._items and self._items[0].age(now) > self.ttl:
            self._items.popleft()
            removed += 1
        return removed

    def live(self, now: float | None = None) -> list[Notification]:
        self.prune(now)
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Notification]:
        return iter(self._items)

    # -- rendering ---------------------------------------------------------

    def _wrap(self, note: Notification, now: float) -> list[str]:
        label = f"[{format_age(note.age(now))}] {note.text}"
        return textwrap.wrap(
            label,
            width=self.profile.columns,
            subsequent_indent=WRAP_INDENT,
            # Keep long unbroken tokens (URLs, paths) from collapsing the layout.
            break_long_words=True,
            break_on_hyphens=False,
        ) or [label]

    def body_lines(self, now: float | None = None) -> list[str]:
        """Wrapped, newest-last body lines, truncated to what fits on screen.

        Truncation drops whole notifications from the top rather than slicing
        one in half: a bare continuation line with its header scrolled off is
        unreadable. The single exception is a notification too tall to fit on
        its own, where the head is kept -- it carries the age and the start of
        the text.
        """
        now = self.now() if now is None else now
        rows = self.profile.rows

        selected: list[str] = []
        for note in reversed(self.live(now)):
            group = self._wrap(note, now)
            if len(selected) + len(group) > rows:
                if not selected:
                    selected = group[:rows]
                break
            selected = group + selected
        return selected

    def header(self, now: float | None = None) -> str:
        now = self.now() if now is None else now
        live = len(self.live(now))
        return f"{live} live / {self.total_seen} seen"

    def screen(self, now: float | None = None) -> str:
        """The payload sent to the device: header, then one line per row."""
        now = self.now() if now is None else now
        return "\n".join([self.header(now), *self.body_lines(now)])
