"""routers/admin_gateway.py — Admin pembayaran online Midtrans (E14). Dijaga require_role('admin').

GET  /api/admin/payment-transactions                 -> [PaymentTransaction]
POST /api/admin/orders/{code}/refund {amount?, reason} -> Order
GET  /api/admin/email-logs                           -> {mode, from_email, items: [EmailLog tanpa html]}
GET  /api/admin/email-logs/{id}                      -> EmailLog (+html untuk pratinjau)
POST /api/admin/email-logs/{id}/resend               -> EmailLog baru (kirim ulang isi yang sama)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core_utils import safe_doc
from db import get_db
from dependencies import get_current_user, require_role
from services import gateway as svc
from services import mailer

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])


class RefundIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    amount: Optional[int] = Field(default=None, gt=0)
    reason: str = Field(default="", max_length=250)


@router.get("/payment-transactions")
async def list_transactions(limit: int = Query(default=200, ge=1, le=500)):
    docs = await get_db().payment_transactions.find({}, {"last_notification": 0}).sort(
        [("created_at", -1)]).to_list(limit)
    return [safe_doc(d) for d in docs]


@router.post("/orders/{code}/refund")
async def refund(code: str, payload: RefundIn, admin=Depends(get_current_user)):
    db = get_db()
    order = await db.orders.find_one({"code": code})
    if not order:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    try:
        return await svc.refund_order(db, admin["id"], order, payload.amount, payload.reason)
    except svc.PaymentError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/email-logs")
async def list_email_logs(limit: int = Query(default=200, ge=1, le=500)):
    docs = await get_db().email_logs.find({}, {"html": 0, "text": 0}).sort([("created_at", -1)]).to_list(limit)
    return {"mode": mailer.mode(), "from_email": mailer.sender()[1] or None, "items": [safe_doc(d) for d in docs]}


async def _log_or_404(log_id):
    doc = await get_db().email_logs.find_one({"id": log_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Log email tidak ditemukan")
    return doc


@router.get("/email-logs/{log_id}")
async def get_email_log(log_id: str):
    return safe_doc(await _log_or_404(log_id))


@router.post("/email-logs/{log_id}/resend")
async def resend_email(log_id: str):
    d = await _log_or_404(log_id)
    log = await mailer.send(get_db(), kind=d["kind"], to=d["to"], subject=d["subject"], html=d.get("html", ""),
                            text=d.get("text", ""), order_code=d.get("order_code"))
    log.pop("html", None)
    log.pop("text", None)
    return log
