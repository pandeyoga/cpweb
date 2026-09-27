"""routers/admin_brands.py — profil brand untuk section Discovery & filter (router TIPIS).

GET    /api/admin/brands                 -> semua brand dari produk + profil
PUT    /api/admin/brands                 -> upsert profil {name, logo, image, desc, order, hidden}
DELETE /api/admin/brands/profile?name=   -> hapus profil (brand tetap ada selama dipakai produk)
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from admin_schemas import AdminBrandInput
from db import get_db
from dependencies import get_current_user, require_role
from services import admin_brands as svc

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])


@router.get("/brands")
async def list_brands():
    return await svc.list_admin(get_db())


@router.put("/brands")
async def upsert_brand(payload: AdminBrandInput, admin=Depends(get_current_user)):
    return await svc.upsert(get_db(), admin["id"], payload.model_dump())


@router.delete("/brands/profile")
async def delete_brand_profile(name: str = Query(min_length=1, max_length=120), admin=Depends(get_current_user)):
    if not await svc.remove(get_db(), admin["id"], name):
        raise HTTPException(status_code=404, detail="Profil brand tidak ditemukan")
    return {"ok": True}
