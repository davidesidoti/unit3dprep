"""TMDB metadata cache — JSON file store. Thread-safe. No sqlite3.

Keys are resolved absolute source_path strings.
Schema per entry:
  { tmdb_id, tmdb_kind, title, year, poster, overview, fetched_at }
"""
import asyncio
import json
import os
import threading
import time
from pathlib import Path

CACHE_PATH = Path(
    os.environ.get("ITA_TMDB_CACHE_PATH", str(Path.home() / ".itatorrents_tmdb_cache.json"))
)
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Sync helpers
# ---------------------------------------------------------------------------

def _load() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _get_sync(source_path: str) -> dict | None:
    with _lock:
        return _load().get(source_path)


def _set_sync(source_path: str, record: dict):
    with _lock:
        data = _load()
        data[source_path] = record
        _save(data)


def _get_many_sync(source_paths: list) -> dict:
    with _lock:
        data = _load()
    return {sp: data[sp] for sp in source_paths if sp in data}


def _delete_sync(source_path: str):
    with _lock:
        data = _load()
        data.pop(source_path, None)
        _save(data)


def _list_all_sync() -> dict:
    with _lock:
        return _load()


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------

async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


async def get_cache(source_path: str) -> dict | None:
    return await _run(_get_sync, source_path)


async def set_cache(source_path: str, **fields):
    record = {**fields, "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())}
    await _run(_set_sync, source_path, record)


async def get_many(source_paths: list) -> dict:
    return await _run(_get_many_sync, [str(sp) for sp in source_paths])


async def delete_cache(source_path: str):
    await _run(_delete_sync, source_path)


async def list_all_cache() -> dict:
    return await _run(_list_all_sync)
