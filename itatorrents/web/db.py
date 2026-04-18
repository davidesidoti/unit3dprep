"""Upload history — JSON file store. No sqlite3 dependency."""
import asyncio
import json
import os
import threading
import time
from pathlib import Path

DB_PATH = Path(os.environ.get("ITA_DB_PATH", str(Path.home() / ".itatorrents_db.json")))
_lock = threading.Lock()


def _load() -> list[dict]:
    if not DB_PATH.exists():
        return []
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(records: list[dict]):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def _init_db_sync():
    with _lock:
        if not DB_PATH.exists():
            _save([])


def _record_upload_sync(
    category, kind, source_path, seeding_path,
    tmdb_id, title, year, final_name, exit_code, hardlink_only=False,
):
    with _lock:
        records = _load()
        # upsert by seeding_path
        for r in records:
            if r["seeding_path"] == seeding_path:
                r["unit3dup_exit_code"] = exit_code
                r["uploaded_at"] = _now_iso()
                r["hardlink_only"] = hardlink_only
                _save(records)
                return
        next_id = max((r.get("id", 0) for r in records), default=0) + 1
        records.append({
            "id": next_id,
            "category": category,
            "kind": kind,
            "source_path": source_path,
            "seeding_path": seeding_path,
            "tmdb_id": tmdb_id or "",
            "title": title or "",
            "year": year or "",
            "final_name": final_name or "",
            "uploaded_at": _now_iso(),
            "unit3dup_exit_code": exit_code,
            "hardlink_only": hardlink_only,
        })
        _save(records)


def _update_exit_code_sync(seeding_path: str, exit_code: int):
    with _lock:
        records = _load()
        for r in records:
            if r["seeding_path"] == seeding_path:
                r["unit3dup_exit_code"] = exit_code
                _save(records)
                return


def _list_uploads_sync() -> list[dict]:
    with _lock:
        records = _load()
    return sorted(records, key=lambda r: r.get("uploaded_at", ""), reverse=True)


def _get_by_seeding_sync(seeding_path: str) -> dict | None:
    with _lock:
        records = _load()
    for r in records:
        if r["seeding_path"] == seeding_path:
            return r
    return None


def _delete_record_sync(seeding_path: str):
    with _lock:
        records = _load()
        records = [r for r in records if r["seeding_path"] != seeding_path]
        _save(records)


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------

async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


async def init_db():
    await _run(_init_db_sync)


async def record_upload(
    *,
    category: str,
    kind: str,
    source_path: str,
    seeding_path: str,
    tmdb_id: str = "",
    title: str = "",
    year: str = "",
    final_name: str = "",
    exit_code: int | None = None,
    hardlink_only: bool = False,
):
    await _run(
        _record_upload_sync,
        category, kind, source_path, seeding_path,
        tmdb_id, title, year, final_name, exit_code, hardlink_only,
    )


async def update_exit_code(seeding_path: str, exit_code: int):
    await _run(_update_exit_code_sync, seeding_path, exit_code)


async def list_uploads() -> list[dict]:
    return await _run(_list_uploads_sync)


async def get_upload_by_seeding_path(seeding_path: str) -> dict | None:
    return await _run(_get_by_seeding_sync, seeding_path)


async def delete_record(seeding_path: str):
    await _run(_delete_record_sync, seeding_path)
