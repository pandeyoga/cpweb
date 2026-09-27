"""routers/admin_content.py — CMS admin (Epic E9). Dijaga require_role('admin') (RC-E10).

  GET  /api/admin/content                       -> {key: data}
  GET  /api/admin/content/schema                -> [section skema]
  PUT  /api/admin/content/{key}                 -> data section (audited)
  GET  /api/admin/content/{key}/revisions       -> [rev...] (E9+)
  GET  /api/admin/content/{key}/revisions/{rid} -> {data} snapshot lengkap (pratinjau)
  POST /api/admin/content/{key}/revert          -> rollback PERSIS ke revisi/default (override lain dihapus)
"""
from fastapi import APIRouter, Body, Depends, HTTPException

from db import get_db
from dependencies import require_role, get_current_user
from services import content as content_svc
from schemas import ContentUpdateIn

router = APIRouter(prefix="/admin/content", tags=["admin-content"],
                   dependencies=[Depends(require_role("admin"))])


@router.get("")
async def list_content():
    return await content_svc.admin_content(get_db())


@router.get("/schema")
async def get_schema():
    return content_svc.content_schema()


@router.put("/{key}")
async def update_content(key: str, payload: ContentUpdateIn, user=Depends(get_current_user)):
    result = await content_svc.update_section(get_db(), key, payload.data or {}, user["id"])
    if result is None:
        raise HTTPException(status_code=404, detail="Section tidak dikenal")
    return {"key": key, "data": result}


@router.get("/{key}/revisions")
async def list_revisions(key: str):
    result = await content_svc.list_revisions(get_db(), key)
    if result is None:
        raise HTTPException(status_code=404, detail="Section tidak dikenal")
    return {"key": key, "revisions": result}


@router.post("/{key}/revert")
async def revert_content(key: str, payload: dict = Body(default={}), user=Depends(get_current_user)):
    """revert: {revision_id?: str, to_default?: bool}.
    revision_id → apply data revisi tersebut. to_default → apply default registry.
    """
    if payload.get("to_default"):
        result = await content_svc.revert_to_default(get_db(), key, user["id"])
        if result is None:
            raise HTTPException(status_code=404, detail="Section tidak dikenal")
        return {"key": key, "data": result, "mode": "default"}
    rev_id = payload.get("revision_id")
    if not rev_id:
        raise HTTPException(status_code=400, detail="revision_id atau to_default wajib")
    result = await content_svc.revert_to_revision(get_db(), key, rev_id, user["id"])
    if result is None:
        raise HTTPException(status_code=404, detail="Revisi tidak ditemukan")
    return {"key": key, "data": result, "mode": "revision", "revision_id": rev_id}


@router.get("/{key}/revisions/{rev_id}")
async def get_revision(key: str, rev_id: str):
    data = await content_svc.revision_snapshot(get_db(), key, rev_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Revisi tidak ditemukan")
    return {"key": key, "revision_id": rev_id, "data": data}
