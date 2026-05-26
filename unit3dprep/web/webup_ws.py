"""Persistent WebSocket listener for Unit3DWebUp /ws.

Spawned in app.py lifespan. Maintains a fan-out registry so the orchestrator
can subscribe per `job_id` (or wildcard) and receive every relevant message
via an asyncio.Queue. Auto-reconnects with exponential backoff.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from .webup_client import base_url


WILDCARD = "*"
_log = logging.getLogger(__name__)


def _ws_url() -> str:
    base = base_url()
    if base.startswith("https://"):
        return "wss://" + base[len("https://"):] + "/ws"
    if base.startswith("http://"):
        return "ws://" + base[len("http://"):] + "/ws"
    return base + "/ws"


class WebupWSManager:
    """Singleton-ish; created in lifespan and stored on app.state.webup_ws."""

    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._connected = asyncio.Event()

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    async def subscribe(self, key: str = WILDCARD) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subs.setdefault(key, []).append(q)
        return q

    async def unsubscribe(self, key: str, q: asyncio.Queue) -> None:
        async with self._lock:
            lst = self._subs.get(key)
            if not lst:
                return
            try:
                lst.remove(q)
            except ValueError:
                pass
            if not lst:
                self._subs.pop(key, None)

    async def rekey(self, old: str, new: str, q: asyncio.Queue) -> None:
        """Move a queue from one key (typically wildcard) to a specific job_id."""
        async with self._lock:
            lst = self._subs.get(old)
            if lst and q in lst:
                lst.remove(q)
                if not lst:
                    self._subs.pop(old, None)
            self._subs.setdefault(new, []).append(q)

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        keys: list[str] = [WILDCARD]
        jid = msg.get("job_id")
        if jid:
            keys.append(str(jid))
        async with self._lock:
            queues: list[asyncio.Queue] = []
            for k in keys:
                queues.extend(self._subs.get(k, []))
        mtype = (msg.get("type") or "").lower()
        if mtype == "posterlogmessage":
            _log.info(
                "webup ws dispatch posterLogMessage job_id=%s msg=%r queues=%d",
                jid, str(msg.get("message") or "")[:80], len(queues),
            )
        for q in queues:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                _log.warning("webup ws queue full, dropping msg for key=%s", jid or WILDCARD)

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            url = _ws_url()
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20, close_timeout=5) as ws:
                    self._connected.set()
                    backoff = 1.0
                    _log.info("webup ws connected: %s", url)
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except (TypeError, ValueError):
                            continue
                        if not isinstance(msg, dict):
                            continue
                        await self._dispatch(msg)
            except (ConnectionClosed, OSError, asyncio.TimeoutError) as e:
                _log.debug("webup ws disconnected: %s", e)
            except Exception as e:
                _log.warning("webup ws error: %s", e)
            finally:
                self._connected.clear()
            if self._stop.is_set():
                break
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 30.0)

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="webup-ws-listener")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
