"""Caricati — seedings tracker."""
import shutil
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ...media import scan_seedings
from ..db import delete_record, list_uploads
from ..templates_env import templates

router = APIRouter()


@router.get("/uploaded", response_class=HTMLResponse)
async def uploaded_page(request: Request):
    seedings = scan_seedings()
    db_records = await list_uploads()
    db_by_path = {r["seeding_path"]: r for r in db_records}

    items = []
    seeding_paths_on_fs = set()
    for p in seedings:
        key = str(p)
        seeding_paths_on_fs.add(key)
        record = db_by_path.get(key)
        items.append({
            "path": p,
            "seeding_path": key,
            "name": p.name,
            "is_dir": p.is_dir(),
            "title": record["title"] if record else "",
            "year": record["year"] if record else "",
            "category": record["category"] if record else "",
            "kind": record["kind"] if record else "",
            "uploaded_at": record["uploaded_at"] if record else "",
            "exit_code": record["unit3dup_exit_code"] if record else None,
            "in_db": record is not None,
            "hardlink_only": record.get("hardlink_only", False) if record else False,
        })

    # Manual marks: DB records with seeding_path starting with __manual__
    manual = [
        r for r in db_records
        if r["seeding_path"].startswith("__manual__:")
    ]

    # Orphaned: in DB, not on disk, not manual
    orphaned = [
        r for r in db_records
        if r["seeding_path"] not in seeding_paths_on_fs
        and not r["seeding_path"].startswith("__manual__:")
    ]

    return templates.TemplateResponse(request, "uploaded.html", {
        "items": items,
        "manual": manual,
        "orphaned": orphaned,
        "active": "uploaded",
    })


@router.post("/uploaded/delete")
async def uploaded_delete(seeding_path: str = Form(...), delete_file: str = Form("1")):
    """Remove DB record and optionally the file/folder from ~/seedings/."""
    # Manual marks: never touch filesystem
    if seeding_path.startswith("__manual__:"):
        await delete_record(seeding_path)
        return JSONResponse({"ok": True})

    # Safety: only allow deletion inside ~/seedings/
    seedings_root = (Path.home() / "seedings").resolve()
    target = Path(seeding_path).resolve()
    if not str(target).startswith(str(seedings_root)):
        return JSONResponse({"ok": False, "error": "Path fuori da ~/seedings/"}, status_code=403)

    # Delete from filesystem if requested and exists
    if delete_file == "1" and target.exists():
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        except OSError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    await delete_record(seeding_path)
    return JSONResponse({"ok": True})
