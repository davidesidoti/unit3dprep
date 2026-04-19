"""In-memory log ring buffer with async subscribers for SSE tail.

Captures records from the root logger (and any child loggers) and emits them
to every subscriber's asyncio.Queue. New SSE clients receive the last
`HISTORY` entries immediately then see live updates.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Deque

HISTORY = 500

_history: Deque[dict] = deque(maxlen=HISTORY)
_subscribers: set[asyncio.Queue] = set()
_main_loop: asyncio.AbstractEventLoop | None = None


def _level_kind(level: int) -> str:
    if level >= logging.ERROR:
        return "error"
    if level >= logging.WARNING:
        return "warn"
    if level >= logging.INFO:
        return "info"
    return "debug"


class _RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": time.strftime("%H:%M:%S", time.gmtime(record.created)),
                "kind": _level_kind(record.levelno),
                "name": record.name,
                "msg": self.format(record),
            }
        except Exception:
            return
        _history.append(entry)
        if _main_loop is None:
            return
        for q in list(_subscribers):
            try:
                _main_loop.call_soon_threadsafe(q.put_nowait, entry)
            except Exception:
                pass


def install(loop: asyncio.AbstractEventLoop) -> None:
    """Attach the ring handler to the root logger. Call once at startup."""
    global _main_loop
    _main_loop = loop
    h = _RingHandler()
    h.setLevel(logging.INFO)
    h.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    for existing in list(root.handlers):
        if isinstance(existing, _RingHandler):
            return
    root.addHandler(h)
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)


def history() -> list[dict]:
    return list(_history)


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def emit(kind: str, msg: str, name: str = "app") -> None:
    """Manual emit helper for business events (upload started, etc.)."""
    entry = {
        "ts": time.strftime("%H:%M:%S", time.gmtime()),
        "kind": kind,
        "name": name,
        "msg": msg,
    }
    _history.append(entry)
    if _main_loop is None:
        return
    for q in list(_subscribers):
        try:
            _main_loop.call_soon_threadsafe(q.put_nowait, entry)
        except Exception:
            pass
