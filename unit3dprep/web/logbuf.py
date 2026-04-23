"""In-memory log ring buffer with async subscribers for SSE tail.

Captures records from the root logger (and any child loggers) and emits them
to every subscriber's asyncio.Queue. New SSE clients receive the last
`HISTORY` entries immediately then see live updates.

Each entry carries:
    ts     - "HH:MM:SS" (GMT)
    kind   - "info" | "ok" | "warn" | "error" | "debug"
    name   - raw logger name (e.g. "httpx", "unit3dup")
    msg    - formatted message
    source - user-facing category: app|http|upload|client|tracker|wizard|unit3dup|system
    event  - optional slug for UI grouping (e.g. "upload.tmdb")
    count  - present when consecutive duplicates were coalesced (>=2)
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Deque

HISTORY = 500
COALESCE_WINDOW = 2.0  # seconds

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


def _infer_source(name: str) -> str:
    n = (name or "").lower()
    if n.startswith("httpx") or n.startswith("httpcore") or n.startswith("urllib3"):
        return "http"
    if n == "unit3dup":
        return "unit3dup"
    if n == "wizard":
        return "wizard"
    if n.startswith("uvicorn") or n.startswith("fastapi") or n.startswith("starlette"):
        return "system"
    if "tracker" in n:
        return "tracker"
    if "client" in n or "qbit" in n:
        return "client"
    if n.startswith("unit3dprep") or n.startswith("itatorrents"):
        return "app"
    return "app"


def _push(entry: dict) -> None:
    """Append to history (with coalescence) and broadcast to subscribers."""
    now = time.time()
    last = _history[-1] if _history else None
    if (
        last is not None
        and last.get("source") == entry.get("source")
        and last.get("event") == entry.get("event")
        and last.get("msg") == entry.get("msg")
        and last.get("kind") == entry.get("kind")
        and (now - last.get("_t", 0)) <= COALESCE_WINDOW
    ):
        last["count"] = int(last.get("count", 1)) + 1
        last["ts"] = entry["ts"]
        last["_t"] = now
        out = {k: v for k, v in last.items() if k != "_t"}
        _broadcast(out)
        return
    entry["_t"] = now
    _history.append(entry)
    out = {k: v for k, v in entry.items() if k != "_t"}
    _broadcast(out)


def _broadcast(entry: dict) -> None:
    if _main_loop is None:
        return
    for q in list(_subscribers):
        try:
            _main_loop.call_soon_threadsafe(q.put_nowait, entry)
        except Exception:
            pass


class _RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": time.strftime("%H:%M:%S", time.gmtime(record.created)),
                "kind": _level_kind(record.levelno),
                "name": record.name,
                "msg": self.format(record),
                "source": _infer_source(record.name),
            }
        except Exception:
            return
        _push(entry)


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
            break
    else:
        root.addHandler(h)
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)

    # Silence noisy HTTP-client loggers: every qBittorrent poll logs a GET/POST
    # at INFO on httpx, which floods the Logs tab. Surface only real problems.
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def history() -> list[dict]:
    return [{k: v for k, v in e.items() if k != "_t"} for e in _history]


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def emit(
    kind: str,
    msg: str,
    name: str = "app",
    *,
    source: str | None = None,
    event: str | None = None,
) -> None:
    """Manual emit helper for business events (upload started, etc.)."""
    entry: dict[str, Any] = {
        "ts": time.strftime("%H:%M:%S", time.gmtime()),
        "kind": kind,
        "name": name,
        "msg": msg,
        "source": source or _infer_source(name),
    }
    if event:
        entry["event"] = event
    _push(entry)
