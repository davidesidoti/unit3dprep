"""Upload history JSON endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...i18n import get_request_lang, t
from ..db import delete_record, delete_records_by_ids, list_uploads

router = APIRouter(prefix="/api", tags=["uploaded"])


class BulkDeleteBody(BaseModel):
    ids: list[int]


@router.get("/uploaded")
async def list_all():
    records = await list_uploads()
    return JSONResponse({"records": records})


@router.delete("/uploaded/{record_id}")
async def delete_by_id(request: Request, record_id: int):
    records = await list_uploads()
    target = next((r for r in records if r.get("id") == record_id), None)
    if target is None:
        raise HTTPException(404, t("err.record_not_found", get_request_lang(request)))
    await delete_record(target["seeding_path"])
    return JSONResponse({"ok": True})


@router.post("/uploaded/bulk-delete")
async def bulk_delete(body: BulkDeleteBody):
    deleted = await delete_records_by_ids(body.ids)
    return JSONResponse({"ok": True, "deleted": deleted})
