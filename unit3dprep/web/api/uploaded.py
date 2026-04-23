"""Upload history JSON endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..db import delete_record, list_uploads

router = APIRouter(prefix="/api", tags=["uploaded"])


@router.get("/uploaded")
async def list_all():
    records = await list_uploads()
    return JSONResponse({"records": records})


@router.delete("/uploaded/{record_id}")
async def delete_by_id(record_id: int):
    records = await list_uploads()
    target = next((r for r in records if r.get("id") == record_id), None)
    if target is None:
        raise HTTPException(404, "Record not found")
    await delete_record(target["seeding_path"])
    return JSONResponse({"ok": True})
