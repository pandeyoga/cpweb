"""routers/gateway.py — Pembayaran online Midtrans Snap (E14). Router TIPIS; logika di services/gateway.py.

GET  /api/payments/config                      -> {enabled, mode, client_key, snap_js_url}
POST /api/orders/{code}/pay?t=                 -> {token, redirect_url, gateway_order_id, mode}
GET  /api/orders/{code}/payment-status?t=      -> Order (setelah sinkron status gateway)
POST /api/orders/{code}/mock-pay?t= {outcome}  -> Order (HANYA mode simulasi)
POST /api/payments/midtrans/notification       -> {ok}  (webhook, signature SHA512 wajib)
Admin (monitor + refund): routers/admin_gateway.py
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from db import get_db
from dependencies import get_optional_user
from services import gateway as svc
from services import midtrans as mt
from services import orders as orders_svc

router = APIRouter(tags=["payments-gateway"])


class MockPayIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    outcome: Literal["settlement", "expire", "deny"]


async def _order(code, user, t):
    order = await orders_svc.get_order_for_user(get_db(), code, user, token=t)
    if not order:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    return order


@router.get("/payments/config")
async def payment_config():
    return mt.public_config()


@router.post("/orders/{code}/pay")
async def pay(code: str, t: Optional[str] = Query(default=None, max_length=64), user=Depends(get_optional_user)):
    order = await _order(code, user, t)
    try:
        return await svc.start_payment(get_db(), order)
    except svc.PaymentError as e:
        status = 503 if "dikonfigurasi" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e))


@router.get("/orders/{code}/payment-status")
async def payment_status(code: str, t: Optional[str] = Query(default=None, max_length=64),
                         user=Depends(get_optional_user)):
    await _order(code, user, t)
    await svc.sync_status(get_db(), code)
    return await _order(code, user, t)


@router.post("/orders/{code}/mock-pay")
async def mock_pay(code: str, payload: MockPayIn, t: Optional[str] = Query(default=None, max_length=64),
                   user=Depends(get_optional_user)):
    await _order(code, user, t)
    try:
        await svc.mock_complete(get_db(), code, payload.outcome)
    except svc.PaymentError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return await _order(code, user, t)


@router.post("/payments/midtrans/notification")
async def midtrans_notification(request: Request):
    try:
        n = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Body tidak valid")
    if not isinstance(n, dict):
        raise HTTPException(status_code=400, detail="Body tidak valid")
    state = await svc.handle_webhook(get_db(), n)
    if state is None:
        raise HTTPException(status_code=403, detail="Signature tidak valid")
    return {"ok": True, "state": state}
