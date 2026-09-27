"""routers/payments.py — Bukti bayar sisi PELANGGAN (Epic E6). Router TIPIS, owner-scoped.

POST /api/orders/{code}/payment-proof?t= {amount, ref?, image_url?} -> PaymentProof  (pemilik / tamu ber-token; 404 selain itu)
POST /api/orders/{code}/payment-proof/upload?t= (multipart file)    -> {url}  (E20; dibatasi sejak stream)
GET  /api/orders/{code}/payment-proofs                          -> [PaymentProof,...] (pemilik atau admin)
Tidak auto-lunas: butuh verifikasi admin. Order terminal/COD → 400. Logika di services/payments.py.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from db import get_db
from dependencies import get_current_user, get_optional_user
from schemas import PaymentProofInput
from services import media as media_svc
from services import orders as orders_svc
from services import payments as svc

router = APIRouter(tags=["payments"])


@router.post("/orders/{code}/payment-proof/upload")
async def upload_proof_image(code: str, file: UploadFile = File(...), t: Optional[str] = Query(default=None, max_length=64),
                             user=Depends(get_optional_user)):
    """Unggah FOTO bukti transfer (E20). Owner-scoped: hanya pemilik pesanan/admin.

    Berkas disimpan lokal (folder 'Bukti Bayar') dan kembalikan {url} untuk dipakai
    pada POST /orders/{code}/payment-proof. Menggantikan input URL manual yang rapuh.
    """
    db = get_db()
    is_admin = (user or {}).get("role") == "admin"
    if not is_admin and not await orders_svc.get_order_for_user(db, code, user, token=t):
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    actor = (user or {}).get("id") or f"guest:{code}"
    try:
        folder = await media_svc.ensure_folder_by_name(db, "Bukti Bayar", actor)
        data = bytearray()
        while chunk := await file.read(1024 * 1024):  # batasi sejak stream, bukan setelah memuat semua
            data.extend(chunk)
            if len(data) > media_svc.MAX_BYTES:
                raise media_svc.MediaError(f"Berkas terlalu besar (maks {media_svc.MAX_BYTES // (1024 * 1024)} MB)")
        data = bytes(data)
        asset = await media_svc.save_upload(
            db, data, file.filename or "bukti.jpg", file.content_type or "",
            actor, folder_id=folder, alt=f"Bukti bayar {code}",
        )
    except media_svc.MediaError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"url": asset["url"], "thumb_url": asset.get("thumb_url"), "id": asset["id"]}


@router.post("/orders/{code}/payment-proof")
async def submit_proof(code: str, payload: PaymentProofInput, t: Optional[str] = Query(default=None, max_length=64),
                       user=Depends(get_optional_user)):
    proof, err = await svc.submit_proof(get_db(), user, code, payload.model_dump(), token=t)
    if err == "notfound":
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    if err == "terminal":
        raise HTTPException(status_code=400, detail="Pesanan sudah final — tak bisa unggah bukti")
    if err == "cod":
        raise HTTPException(status_code=400, detail="Pesanan COD tidak memerlukan bukti transfer")
    if err == "online":
        raise HTTPException(status_code=400, detail="Pembayaran online diverifikasi otomatis — tak perlu bukti")
    if err == "overpaid":
        raise HTTPException(status_code=400, detail="Jumlah melebihi sisa tagihan pesanan")
    return proof


@router.get("/orders/{code}/payment-proofs")
async def list_order_proofs(code: str, user=Depends(get_current_user)):
    db = get_db()
    doc = await db.orders.find_one({"code": code})
    if not doc:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    is_admin = user.get("role") == "admin"
    if not is_admin and doc.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
    return await svc.list_proofs_for_order(db, code)
