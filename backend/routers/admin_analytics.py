"""routers/admin_analytics.py — Admin Growth: analytics aggregates + CRM segments (Epic E7).

Semua di bawah /api/admin dan DIJAGA require_role('admin') (RC-E10). READ-only
(tak ada mutasi → tak ada audit). Data diturunkan dari events/orders (SSOT).
"""
from fastapi import APIRouter, Depends, Query, Response

from db import get_db
from dependencies import require_role
from services import analytics as analytics_svc
from services import crm as crm_svc

router = APIRouter(prefix="/admin", tags=["admin-growth"],
                   dependencies=[Depends(require_role("admin"))])


@router.get("/analytics")
async def analytics(range: int = 30):
    r = max(1, min(int(range or 30), 365))
    return await analytics_svc.aggregates(get_db(), r)


@router.get("/crm/segments")
async def crm_segments(type: str = "", skip: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=1000)):
    """Berhalaman (butir 9): {segments, total, rows[skip:skip+limit]}. LTV = paid − refunded."""
    return await crm_svc.segments(get_db(), str(type or "")[:40], skip=skip, limit=limit)


@router.get("/crm/export")
async def crm_export(type: str = ""):
    """CSV LENGKAP (semua baris, tanpa batas halaman)."""
    data = await crm_svc.segments(get_db(), str(type or "")[:40], all_rows=True)
    return Response(content=crm_svc.to_csv(data["rows"]), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="crm-pelanggan.csv"'})
