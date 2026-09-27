"""services/order_helpers.py — helper internal order lifecycle (dipisah dari orders.py).

Berisi: exceptions domain order, derivasi payment_status (INV-5), snapshot item
(harga/nama/varian SAAT beli), klaim/rilis slot voucher per-user (atomik, race-safe),
dan sanitasi alamat. Modul ini di-re-export oleh `services/orders.py` agar API publik
(`services.orders.OrderError`, dst.) TIDAK berubah (guardrail <=300 baris/berkas).
"""
import hashlib
import json

from pymongo.errors import DuplicateKeyError

from core_utils import money, new_id, now_iso, safe_doc
from services import variants as V


class OrderError(Exception):
    """400 — input/aturan bisnis (mis. produk tak ada, voucher tak berlaku)."""


class IdempotencyConflict(OrderError):
    """409 — Idempotency-Key yang sama dipakai untuk isi pesanan berbeda."""


def order_fingerprint(uid, items_in, address, shipping_id, payment, voucher_code, note, email):
    """Sidik isi checkout: key idempotensi hanya boleh me-replay pesanan yang identik."""
    items = sorted([str(i.get("product_id")), str(i.get("sku") or ""), str(i.get("variant_type") or ""),
                    str(i.get("volume_ml") or ""), int(i.get("quantity") or 0)] for i in items_in)
    raw = json.dumps([uid, items, _clean_address(address), shipping_id, payment or {},
                      str(voucher_code or "").strip().upper(), str(note or "")[:500],
                      str(email or "").strip().lower()], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class StockConflict(Exception):
    """409 — stok tak cukup (anti-oversell). Membawa detail baris yang gagal."""

    def __init__(self, item, available=None):
        self.item = item or {}
        self.available = available
        super().__init__("stock_conflict")


class InvalidTransition(Exception):
    """400 — transisi status di luar LEGAL_TRANSITIONS (RC-E7/E8)."""


def derive_payment_status(paid_amount, total):
    paid = money(paid_amount)
    total = money(total)
    if paid <= 0:
        return "belum_bayar"
    if total > 0 and paid >= total:
        return "lunas"
    return "dp"


async def _build_snapshot(db, items_in):
    """Bangun item order (snapshot harga/nama/gambar SAAT beli). Raise OrderError bila FK/varian salah.

    Resolusi varian: prioritas `sku` (baru); fallback legacy (variant_type + volume_ml).
    Stok/harga mengacu ke `variants[]` (SSOT). `volume_ml` diturunkan dari dimensi ukuran.
    """
    snapshot = []
    for it in items_in:
        pid = it.get("product_id")
        sku_in = str(it.get("sku") or "").strip() or None
        vtype = str(it.get("variant_type", "") or "")
        try:
            qty = int(it.get("quantity"))
            ml_in = it.get("volume_ml")
            ml_in = int(ml_in) if ml_in not in (None, "") else None
        except (TypeError, ValueError):
            raise OrderError("Item tidak valid")
        if not pid or qty <= 0:
            raise OrderError("Item tidak valid")
        prod_raw = await db.products.find_one({"id": pid, "status": "active"})
        if not prod_raw:
            raise OrderError(f"Produk tidak ditemukan: {pid}")
        had_variants = bool(prod_raw.get("variants"))
        prod = V.serialize_product(safe_doc(prod_raw))
        if not had_variants:
            # Migrasi lazy write-through: produk legacy (volumes-only) dipersist ke model
            # N-dimensi. Tanpa ini stok atomik per-SKU (services/stock.py) tak menemukan
            # varian di DB sehingga produk legacy MUSTAHIL di-checkout (selalu 409).
            # Guard $exists/$size menjadikan hanya satu penulis menang saat race; SKU
            # derive deterministik sehingga hasil paralel identik.
            await db.products.update_one(
                {"id": pid, "$or": [{"variants": {"$exists": False}},
                                    {"variants": {"$size": 0}}]},
                {"$set": {"options": prod.get("options", []),
                          "variants": prod.get("variants", []),
                          "volumes": prod.get("volumes", []),
                          "updated_at": now_iso()}},
            )
        variant = V.resolve_variant(prod, sku=sku_in, variant_type=vtype, volume_ml=ml_in)
        if not variant:
            label = sku_in or f"{vtype} {ml_in}ml".strip()
            raise OrderError(f"Varian {label} tidak tersedia untuk {prod.get('name')}")
        v_opts = variant.get("options") or {}
        ml = V.parse_ml(v_opts.get(V.SIZE_NAME)) or (ml_in or 0)
        # fallback ml dari dimensi ukuran apa pun namanya
        if ml <= 0:
            for o in prod.get("options", []):
                if V.is_size_dim(o.get("name")):
                    ml = V.parse_ml(v_opts.get(o["name"]))
                    break
        snapshot.append({
            "product_id": pid,
            "slug": prod.get("slug", ""),
            "name": prod.get("name", ""),
            "category": prod.get("category", ""),  # untuk bottle-art FE + scope INV-3
            "image": (prod.get("images") or [None])[0],
            "concentration": prod.get("concentration"),
            "variant_type": V.composite_type(v_opts, prod.get("options", [])),
            "sku": variant.get("sku"),
            "options": v_opts,
            "volume_ml": ml if ml > 0 else 1,
            "unit_price": money(variant.get("price", 0)),
            "quantity": qty,
        })
    return snapshot


async def _claim_per_user_voucher(db, code, user_id, limit):
    """Klaim SATU slot pemakaian voucher per-user secara ATOMIK & race-safe (RC-E2).

    Menegakkan `per_user_limit` TANPA TOCTOU: (1) pastikan dokumen counter ada
    (idempotent, dijaga unique index `(voucher_code,user_id)`), (2) `$inc` ber-guard
    `count < limit` yang dievaluasi atomik oleh MongoDB. Dua checkout paralel milik
    user yang sama TIDAK bisa menembus batas — hanya sejumlah `limit` yang sukses.

    Return True bila slot berhasil diklaim; False bila batas per-user tercapai.
    """
    # 1) Pastikan counter ada. Inisialisasi dari jumlah redemption historis agar
    #    data lama (bila ada) tetap benar. $setOnInsert => idempotent & aman re-run.
    try:
        existing = await db.voucher_redemptions.count_documents(
            {"voucher_code": code, "user_id": user_id}
        )
        await db.voucher_user_usage.update_one(
            {"voucher_code": code, "user_id": user_id},
            {"$setOnInsert": {
                "voucher_code": code, "user_id": user_id,
                "count": int(existing), "created_at": now_iso(),
            }},
            upsert=True,
        )
    except DuplicateKeyError:
        pass  # dibuat oleh request paralel — lanjut ke guarded $inc

    # 2) Guarded atomic increment (anti-race). Hanya sukses bila count < limit.
    res = await db.voucher_user_usage.update_one(
        {"voucher_code": code, "user_id": user_id, "count": {"$lt": int(limit)}},
        {"$inc": {"count": 1}},
    )
    return res.modified_count == 1


async def _release_per_user_voucher(db, code, user_id):
    """Kembalikan satu slot per-user (kompensasi saat insert order gagal)."""
    await db.voucher_user_usage.update_one(
        {"voucher_code": code, "user_id": user_id, "count": {"$gt": 0}},
        {"$inc": {"count": -1}},
    )


async def _release_voucher(db, order):
    """Kembalikan kuota voucher order yang dibatalkan (SALES-07). Idempoten via flag
    `voucher_released` (compare-and-set) → used_count/redemption/per-user turun tepat sekali."""
    code = order.get("voucher_code")
    if not code:
        return
    res = await db.orders.update_one({"code": order["code"], "voucher_released": {"$ne": True}},
                                     {"$set": {"voucher_released": True}})
    if res.modified_count != 1:
        return
    await db.vouchers.update_one({"code": code, "used_count": {"$gt": 0}}, {"$inc": {"used_count": -1}})
    await db.voucher_redemptions.delete_one({"order_code": order["code"]})
    if order.get("user_id"):
        await _release_per_user_voucher(db, code, order["user_id"])


async def _track_purchase(db, order):
    """Event analytics `purchase` dicatat SERVER saat order lunas/paid, 1× per order (SALES-14)."""
    await db.analytics_events.update_one(
        {"type": "purchase", "order_code": order["code"]},
        {"$setOnInsert": {"id": new_id("evt"), "type": "purchase", "order_code": order["code"],
                          "path": "server", "product_id": None, "session_hint": None,
                          "meta": {"value": int(order.get("total", 0) or 0)}, "created_at": now_iso()}},
        upsert=True)


def _clean_address(address):
    a = address or {}
    return {
        "name": str(a.get("name", ""))[:120],
        "phone": str(a.get("phone", ""))[:40],
        "street": str(a.get("street", ""))[:300],
        "district": str(a.get("district", "") or "")[:120],
        "city": str(a.get("city", ""))[:120],
        "province": str(a.get("province", ""))[:120],
        "postal": str(a.get("postal", "") or "")[:12],
        "label": str(a.get("label", "Rumah") or "Rumah")[:40],
    }



async def backfill_guest_tokens(db, limit=5000):
    """SALES-19: order tamu lama (sebelum BUG-SALES-01) diberi access_token agar link bisa dibuka."""
    import secrets
    n = 0
    async for o in db.orders.find({"user_id": None, "access_token": {"$exists": False}},
                                  {"code": 1}).limit(limit):
        res = await db.orders.update_one({"code": o["code"], "access_token": {"$exists": False}},
                                         {"$set": {"access_token": secrets.token_urlsafe(24)}})
        n += res.modified_count
    return n


__all__ = [
    "OrderError", "IdempotencyConflict", "order_fingerprint", "StockConflict", "InvalidTransition", "derive_payment_status",
    "_build_snapshot", "_claim_per_user_voucher", "_release_per_user_voucher", "_release_voucher",
    "_clean_address", "_track_purchase", "backfill_guest_tokens",
]
