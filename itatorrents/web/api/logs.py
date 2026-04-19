"""Log tail SSE + history dump."""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from .. import logbuf

router = APIRouter(prefix="/api", tags=["logs"])


@router.get("/logs/history")
async def history():
    return JSONResponse({"lines": logbuf.history()})


@router.get("/logs/stream")
async def stream(request: Request):
    q = logbuf.subscribe()

    async def gen() -> AsyncGenerator[dict, None]:
        # Replay history first so freshly opened tabs see context
        for entry in logbuf.history():
            yield {"event": "line", "data": json.dumps(entry)}
        try:
            while True:
                if await request.is_disconnected():
                    return
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield {"event": "line", "data": json.dumps(entry)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            logbuf.unsubscribe(q)

    return EventSourceResponse(gen())
