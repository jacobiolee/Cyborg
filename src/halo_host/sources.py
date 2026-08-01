"""Where notifications come from.

A source is anything with a `name` and a `poll()` that returns whatever lines
have appeared since the last call. Polling (rather than callbacks) keeps the
whole pipeline single-threaded and testable; `CommandSource` does use a reader
thread, but only to keep its queue fed.
"""

from __future__ import annotations

import queue
import subprocess
import threading
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Source(Protocol):
    name: str

    def poll(self) -> Iterable[str]:
        """Return lines produced since the previous poll (possibly empty)."""
        ...


class IterableSource:
    """Replays a fixed sequence, `per_poll` lines at a time.

    Deterministic, so it is what the demo and the tests use.
    """

    def __init__(
        self, lines: Iterable[str], name: str = "demo", per_poll: int = 1
    ) -> None:
        self.name = name
        self.per_poll = per_poll
        self._remaining: Iterator[str] = iter(list(lines))

    def poll(self) -> list[str]:
        out = []
        for _ in range(self.per_poll):
            try:
                out.append(next(self._remaining))
            except StopIteration:
                break
        return out

    @property
    def exhausted(self) -> bool:
        peek = next(self._remaining, None)
        if peek is None:
            return True
        self._remaining = iter([peek, *self._remaining])
        return False


class FileTailSource:
    """Follows a file the way `tail -f` does.

    Starts at EOF by default so a pre-existing log does not flood the display
    on startup. Handles truncation (log rotation) by seeking back to 0.
    """

    def __init__(
        self, path: str | Path, name: str | None = None, from_start: bool = False
    ) -> None:
        self.path = Path(path)
        self.name = name or self.path.name
        self._offset = 0
        self._ino: int | None = None
        self._mtime_ns: int | None = None
        if not from_start and self.path.exists():
            st = self.path.stat()
            self._offset = st.st_size
            self._ino, self._mtime_ns = st.st_ino, st.st_mtime_ns

    def _rotated(self, st) -> bool:
        """Did the file get replaced rather than appended to?

        Size alone is not enough: a log rewritten to coincidentally the same
        length looks identical. Inode catches replacement, and an mtime change
        with no size change catches in-place rewrites.
        """
        if self._ino is not None and st.st_ino != self._ino:
            return True
        if st.st_size < self._offset:
            return True
        return (
            st.st_size == self._offset
            and self._mtime_ns is not None
            and st.st_mtime_ns != self._mtime_ns
        )

    def poll(self) -> list[str]:
        if not self.path.exists():
            return []
        st = self.path.stat()
        if self._rotated(st):
            self._offset = 0
        self._ino, self._mtime_ns = st.st_ino, st.st_mtime_ns
        if st.st_size == self._offset:
            return []
        with self.path.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(self._offset)
            data = fh.read()
            self._offset = fh.tell()
        return data.splitlines()


class CommandSource:
    """Streams stdout of a long-running command, e.g. `journalctl -f -n0`.

    A daemon thread drains the pipe into a queue so `poll()` never blocks.
    """

    def __init__(self, command: str | list[str], name: str | None = None) -> None:
        self.command = command
        self.name = name or (
            command if isinstance(command, str) else " ".join(command)
        )[:32]
        self._queue: queue.Queue[str] = queue.Queue()
        self._proc = subprocess.Popen(
            command,
            shell=isinstance(command, str),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _drain(self) -> None:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            self._queue.put(line.rstrip("\n"))

    def poll(self) -> list[str]:
        out = []
        while True:
            try:
                out.append(self._queue.get_nowait())
            except queue.Empty:
                return out

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:  # pragma: no cover
                self._proc.kill()
