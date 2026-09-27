"""routers/admin_orders.py — Admin proses pesanan (Epic E5 BR-6). Router TIPIS.

GET /api/admin/orders?status         -> [Order,...] (semua user)
GET /api/admin/orders/{code}          -> Order (+ allowed_transitions, SALES-18)
PUT /api/admin/orders/{code}/status   -> Order   (HANYA via transition_order; ilegal -> 400;
                                                    shipped WAJIB {courier, tracking_number})
GET /api/admin/couriers               -> [Courier]
PUT /api/admin/orders/{code}/shipment -> Order   (koreksi resi saat shipped → email ulang otomatis)

Admin = pemanggil transition_order (SSOT lifecycle) — BUKAN jalur kedua ubah status (anti RC-E7).
Dijaga require_role('admin').
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from admin_schemas import OrderStatusInput, ShipmentInput
from core_utils import safe_doc
from db import get_db
from dependencies import get_current_user, require_role
from schemas import ORDER_STATUSES
from services import orders as orders_svc
from services import shipment as shipment_svc
from services.audit import log_action

router = APIRouter(prefix="/admin", tags=["admin"],
                   dependencies=[Depends(require_role("admin"))])

LIST_MAX = 500


def _with_allowed(order):
    """SALES-18: transisi yang sah dikirim backend (FE tak lagi menduplikasi LEGAL_TRANSITIONS).
    `paid` non-COD hanya muncul bila sudah lunas (paid hanya dari pembayaran, BUG-SALES-03)."""
    nxt = orders_svc.LEGAL_TRANSITIONS.get(order.get("status"), set())
    is_cod = (order.get("payment") or {}).get("group") == "cod"
    order["allowed_transitions"] = [
        s for s in ORDER_STATUSES
        if s in nxt and (s != "paid" or is_cod or order.get("payment_status") == "lunas")
    ]
    return order


async def _load(db, code):
    doc = await db.orders.find_one({"code": code})
    if not doc:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    return doc


@router.get("/orders")
async def list_orders(response: Response, status: Optional[str] = Query(default=None),
                      q: Optional[str] = Query(default=None, max_length=80),
                      skip: int = Query(default=0, ge=0, le=1000000),
                      limit: int = Query(default=50, ge=1, le=LIST_MAX)):
    """Terpaginasi (butir 5): X-Total-Count = total hasil filter; q = kode/email/nama/telepon."""
    db = get_db()
    filt = {"status": {"$ne": "reserving"}}  # draf reservasi internal tak ditampilkan
    if status in ORDER_STATUSES:
        filt["status"] = status
    if q and q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        filt["$or"] = [{"code": rx}, {"email": rx}, {"address.name": rx}, {"address.phone": rx}]
    response.headers["X-Total-Count"] = str(await db.orders.count_documents(filt))
    docs = await db.orders.find(filt).sort([("created_at", -1), ("code", -1)]).skip(skip).limit(limit).to_list(limit)
    return [safe_doc(d) for d in docs]


@router.get("/orders/{code}")
async def get_order(code: str):
    return _with_allowed(safe_doc(await _load(get_db(), code)))


@router.put("/orders/{code}/status")
async def set_status(code: str, payload: OrderStatusInput, admin=Depends(get_current_user)):
    db = get_db()
    doc = await _load(db, code)
    try:
        if payload.status == "shipped":  # resi wajib (E16)
            result = await shipment_svc.ship_order(db, doc, payload.courier, payload.tracking_number)
        else:
            result = await orders_svc.transition_order(db, doc, payload.status, reason="admin")
    except (orders_svc.InvalidTransition, shipment_svc.ShipmentError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    await log_action(admin["id"], "status", "orders", code, {"to": payload.status})
    return _with_allowed(result)


@router.get("/couriers")
async def list_couriers():
    return shipment_svc.COURIERS


@router.put("/orders/{code}/shipment")
async def update_shipment(code: str, payload: ShipmentInput, admin=Depends(get_current_user)):
    db = get_db()
    doc = await _load(db, code)
    old = doc.get("shipment") or {}
    try:
        result = await shipment_svc.update_shipment(db, doc, payload.courier, payload.tracking_number)
    except shipment_svc.ShipmentError as e:
        raise HTTPException(status_code=400, detail=str(e))
    new = result.get("shipment") or {}
    await log_action(admin["id"], "shipment", "orders", code, {
        "from": {"courier": old.get("courier"), "tracking_number": old.get("tracking_number")},
        "to": {"courier": new.get("courier"), "tracking_number": new.get("tracking_number")},
    })
    return _with_allowed(result)
