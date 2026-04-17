"""SQLite upload history — stdlib sqlite3 + executor (no aiosqlite)."""
import asyncio
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("ITA_DB_PATH", str(Path.home() / ".itatorrents.db")))

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS uploads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,
    kind            TEXT NOT NULL,
    source_path     TEXT NOT NULL,
    seeding_path    TEXT NOT NULL UNIQUE,
    tmdb_id         TEXT,
    title           TEXT,
    year            TEXT,
    final_name      TEXT,
    uploaded_at     TEXT NOT NULL DEFAULT (datetime('now')),
    unit3dup_exit_code INTEGER
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db_sync():
    with _connect() as conn:
        conn.execute(CREATE_SQL)
        conn.commit()


def _record_upload_sync(
    category, kind, source_path, seeding_path,
    tmdb_id, title, year, final_name, exit_code,
):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO uploads
                (category, kind, source_path, seeding_path, tmdb_id,
                 title, year, final_name, unit3dup_exit_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(seeding_path) DO UPDATE SET
                unit3dup_exit_code = excluded.unit3dup_exit_code,
                uploaded_at = datetime('now')
            """,
            (category, kind, source_path, seeding_path,
             tmdb_id, title, year, final_name, exit_code),
        )
        conn.commit()


def _update_exit_code_sync(seeding_path: str, exit_code: int):
    with _connect() as conn:
        conn.execute(
            "UPDATE uploads SET unit3dup_exit_code = ? WHERE seeding_path = ?",
            (exit_code, seeding_path),
        )
        conn.commit()


def _list_uploads_sync() -> list[dict]:
    with _connect() as conn:
        cur = conn.execute("SELECT * FROM uploads ORDER BY uploaded_at DESC")
        return [dict(r) for r in cur.fetchall()]


def _get_by_seeding_sync(seeding_path: str) -> dict | None:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT * FROM uploads WHERE seeding_path = ?", (seeding_path,)
        )
        row = cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Async wrappers (run sync fns in thread pool to avoid blocking event loop)
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
):
    await _run(
        _record_upload_sync,
        category, kind, source_path, seeding_path,
        tmdb_id, title, year, final_name, exit_code,
    )


async def update_exit_code(seeding_path: str, exit_code: int):
    await _run(_update_exit_code_sync, seeding_path, exit_code)


async def list_uploads() -> list[dict]:
    return await _run(_list_uploads_sync)


async def get_upload_by_seeding_path(seeding_path: str) -> dict | None:
    return await _run(_get_by_seeding_sync, seeding_path)
