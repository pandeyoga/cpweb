"""services/payments.py — bukti bayar (Epic E6). Owner submit, admin verify/reject.

SSOT uang = services.orders.record_payment (menaikkan paid_amount → turunkan payment_status;
maju ke `paid` via transition_order bila lunas). Verifikasi IDEMPOTEN per-bukti (INV-P1, butir 12):
`pending` → `processing` (CAS) → record_payment(ref=id bukti, idempoten) → `verified`.
Proses mati di tengah → rekonsiliasi melanjutkan bukti `processing` basi tanpa dobel.
Tamu (order tanpa akun) boleh unggah bukti dengan access token order (butir 5).
"""
from datetime import datetime, timedelta, timezone

from core_utils import new_id, now_iso, safe_doc
from services import orders as orders_svc
from services.audit import log_action

LIST_MAX = 500


async def _owned_order(db, code, user, token=None):
    """Order milik user, atau order tamu dengan access token cocok (IDOR-safe RC-E10)."""
    doc = await orders_svc.get_order_for_user(db, code, user, token=token)
    return (doc, None) if doc else (None, "notfound")


async def submit_proof(db, user, code, data, token=None):
    order, err = await _owned_order(db, code, user, token)
    if err or not order:
        return None, "notfound"
    if order.get("status") in orders_svc.TERMINAL:
        return None, "terminal"
    if (order.get("payment") or {}).get("group") == "cod":
        return None, "cod"
    if (order.get("payment") or {}).get("group") not in ("transfer", "ewallet"):
        return None, "online"  # bayar online diverifikasi otomatis oleh Midtrans
    if int(data["amount"]) > int(order.get("total", 0)) - int(order.get("paid_amount", 0) or 0):
        return None, "overpaid"  # BUG-SALES-04
    proof = {
        "id": new_id("pay"),
        "order_code": code,
        "user_id": (user or {}).get("id"),
        "amount": int(data["amount"]),
        "ref": (data.get("ref") or None),
        "image_url": (data.get("image_url") or None),
        "status": "pending",
        "note": None,
        "verified_by": None,
        "created_at": now_iso(),
        "verified_at": None,
    }
    await db.payment_proofs.insert_one(proof)
    await log_action((user or {}).get("id", "guest"), "submit", "payment_proofs", proof["id"], {"order": code})
    return safe_doc(proof), None


async def list_proofs_for_order(db, code):
    docs = await db.payment_proofs.find({"order_code": code}).sort([("created_at", 1)]).to_list(LIST_MAX)
    return [safe_doc(d) for d in docs]


async def list_proofs(db, status=None):
    filt = {}
    if status in ("pending", "processing", "verified", "rejected"):
        filt["status"] = status
    docs = await db.payment_proofs.find(filt).sort([("created_at", -1)]).to_list(LIST_MAX)
    return [safe_doc(d) for d in docs]


async def verify_proof(db, admin_id, proof_id, approve, note=None):
    proof = await db.payment_proofs.find_one({"id": proof_id})
    if not proof:
        return None, "notfound"
    order = await db.orders.find_one({"code": proof["order_code"]})
    if not order:
        return None, "notfound"
    if order.get("status") in orders_svc.TERMINAL:
        return None, "terminal"  # INV-P2 / RC-E8
    # Idempoten: hanya bukti `pending` yang diklaim (guard atomik anti double-count / INV-P1).
    res = await db.payment_proofs.update_one(
        {"id": proof_id, "status": "pending"},
        {"$set": {"status": "processing" if approve else "rejected", "verified_by": admin_id,
                  "verified_at": now_iso(), "note": (note or None)}},
    )
    if res.modified_count != 1:
        return None, "processed"
    await log_action(admin_id, ("verify" if approve else "reject"),
                     "payment_proofs", proof_id, {"order": proof["order_code"]})
    if approve:
        return await _apply_proof(db, {**proof, "status": "processing"})
    return safe_doc(await db.orders.find_one({"code": proof["order_code"]})), None


async def _apply_proof(db, proof):
    """processing → verified. Aman diulang (record_payment ber-penanda id bukti)."""
    order = await db.orders.find_one({"code": proof["order_code"]})
    try:
        fresh = await orders_svc.record_payment(db, order, proof["amount"], source="proof", ref=proof["id"])
    except (orders_svc.InvalidTransition, orders_svc.OrderError) as e:
        # terminal di tengah jalan / melebihi sisa tagihan — kembalikan bukti ke pending.
        await db.payment_proofs.update_one(
            {"id": proof["id"], "status": "processing"},
            {"$set": {"status": "pending", "verified_by": None, "verified_at": None}})
        return None, ("terminal" if isinstance(e, orders_svc.InvalidTransition) else "overpaid")
    await db.payment_proofs.update_one({"id": proof["id"], "status": "processing"},
                                       {"$set": {"status": "verified"}})
    return fresh, None


async def resume_processing(db, min_age_minutes=2):
    """Rekonsiliasi: bukti `processing` basi (proses mati setelah klaim) → selesaikan."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=min_age_minutes)).isoformat()
    done = []
    for p in await db.payment_proofs.find({"status": "processing", "verified_at": {"$lt": cutoff}}).to_list(200):
        await _apply_proof(db, p)
        done.append(p["id"])
    return done
