"""Audio language cache — JSON file store. Thread-safe. No sqlite3.

Keys are source_path strings (unresolved for series/seasons, same convention as tmdb_cache).
Schema per entry:
  {
    "langs": ["ITA", "ENG", ...],
    "episode_langs": { "<str(filepath)>": ["ITA", "ENG"] },  # only for series/seasons
    "scanned_at": "YYYY-MM-DD HH:MM:SS"
  }
"""
import asyncio
import json
import os
import threading
import time
from pathlib import Path

_lock = threading.Lock()


def _cache_path() -> Path:
    default = str(Path.home() / ".unit3dprep_lang_cache.json")
    try:
        from . import config
        return Path(config.runtime_setting("U3DP_LANG_CACHE_PATH", default=default))
    except Exception:
        from ._env import env as _env
        return Path(_env("U3DP_LANG_CACHE_PATH", "ITA_LANG_CACHE_PATH", default) or default)


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


async def get_lang(source_path: str) -> dict | None:
    return await _run(_get_sync, source_path)


async def set_lang(source_path: str, langs: list, episode_langs: dict | None = None):
    record: dict = {
        "langs": langs,
        "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
    }
    if episode_langs is not None:
        record["episode_langs"] = episode_langs
    await _run(_set_sync, source_path, record)


async def get_many_langs(source_paths: list) -> dict:
    return await _run(_get_many_sync, [str(sp) for sp in source_paths])


async def delete_lang(source_path: str):
    await _run(_delete_sync, source_path)


async def list_all_langs() -> dict:
    return await _run(_list_all_sync)
