"""\"To-check\" flags — JSON file store. Mirrors db.py; no sqlite3 dependency.

Marks media (movies, episodes, seasons, whole series) that the user wants to
re-check later — typically because they lack an Italian audio track and can't be
uploaded to ITT yet. Kept separate from db.py so the upload history / Uploaded
view and the ``uploaded_paths`` enrichment set stay clean.
"""
import asyncio
import json
import threading
import time
from pathlib import Path

_lock = threading.Lock()


def _store_path() -> Path:
    """Re-resolve on every call so UI edits take effect without restart."""
    default = str(Path.home() / ".unit3dprep_tocheck.json")
    try:
        from . import config
        return Path(config.runtime_setting("U3DP_TOCHECK_PATH", default=default))
    except Exception:
        from ._env import env as _env
        return Path(_env("U3DP_TOCHECK_PATH", None, default) or default)


def _load() -> list[dict]:
    path = _store_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(records: list[dict]):
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def _init_sync():
    with _lock:
        if not _store_path().exists():
            _save([])


def _add_flag_sync(source_path: str, category: str, kind: str):
    with _lock:
        records = _load()
        for r in records:
            if r.get("source_path") == source_path:
                r["category"] = category
                r["kind"] = kind
                r["marked_at"] = _now_iso()
                _save(records)
                return
        records.append({
            "source_path": source_path,
            "category": category,
            "kind": kind,
            "marked_at": _now_iso(),
        })
        _save(records)


def _remove_flag_sync(source_path: str):
    with _lock:
        records = _load()
        new = [r for r in records if r.get("source_path") != source_path]
        if len(new) != len(records):
            _save(new)


def _list_flagged_sync() -> list[dict]:
    with _lock:
        records = _load()
    return sorted(records, key=lambda r: r.get("marked_at", ""), reverse=True)


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------

async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


async def init_tocheck():
    await _run(_init_sync)


async def add_flag(source_path: str, category: str, kind: str):
    await _run(_add_flag_sync, source_path, category, kind)


async def remove_flag(source_path: str):
    await _run(_remove_flag_sync, source_path)


async def list_flagged() -> list[dict]:
    return await _run(_list_flagged_sync)


async def list_flagged_paths() -> set[str]:
    records = await _run(_list_flagged_sync)
    return {r["source_path"] for r in records if r.get("source_path")}
