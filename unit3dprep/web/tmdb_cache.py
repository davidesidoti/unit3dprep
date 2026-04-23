"""TMDB metadata cache — JSON file store. Thread-safe. No sqlite3.

Keys are resolved absolute source_path strings.
Schema per entry (all fields optional for backward compat — read with .get()):
  { tmdb_id, tmdb_kind,
    title,          # primary lang (TMDB_DEFAULT_LANG, default it-IT)
    title_en,       # en-US title
    original_title, # TMDB original_title / original_name
    year, poster,
    overview,       # primary lang
    overview_en,    # en-US
    fetched_at }
"""
import asyncio
import json
import os
import threading
import time
from pathlib import Path

_lock = threading.Lock()


def _cache_path() -> Path:
    default = str(Path.home() / ".unit3dprep_tmdb_cache.json")
    try:
        from . import config
        return Path(config.runtime_setting("U3DP_TMDB_CACHE_PATH", default=default))
    except Exception:
        from ._env import env as _env
        return Path(_env("U3DP_TMDB_CACHE_PATH", "ITA_TMDB_CACHE_PATH", default) or default)


CACHE_PATH = _cache_path()


# ---------------------------------------------------------------------------
# Sync helpers
# ---------------------------------------------------------------------------

def _load() -> dict:
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict):
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
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
