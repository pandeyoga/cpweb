"""services/stock.py — STOK ATOMIK per-SKU (anti-oversell, RC-E3) + reservasi idempoten per order.

SSOT stok = `products.variants[].stock` (identitas varian = `sku`).

Reservasi ber-penanda (butir 4/11): setiap pengurangan stok untuk sebuah order menulis penanda
`"<order_code>|<sku>"` ke `products.stock_holds` DALAM update dokumen yang sama dengan `$inc`
(satu dokumen = atomik tanpa transaksi). Akibatnya:
  - reserve() diulang (retry/crash) tak pernah mengurangi dua kali (filter `stock_holds $ne penanda`);
  - release() diulang tak pernah menambah dua kali (filter `stock_holds == penanda` + `$pull`);
  - commit() (order selesai) membuang penanda tanpa mengubah stok.
Order lama (tanpa penanda, `hold_v` < 2) memakai jalur legacy restore() sekali (dijaga flag order).
"""
from core_utils import money


def _norm(items):
    """Normalisasi baris {product_id, sku, quantity} → int aman (qty>0)."""
    out = []
    for it in (items or []):
        pid = it.get("product_id")
        sku = str(it.get("sku") or "").strip()
        try:
            qty = int(it.get("quantity"))
        except (TypeError, ValueError):
            continue
        if pid and sku and qty > 0:
            out.append({"product_id": pid, "sku": sku, "quantity": qty})
    return out


def _merged(items):
    """Satukan baris ber-SKU sama (satu penanda per order×SKU)."""
    acc = {}
    for it in _norm(items):
        k = (it["product_id"], it["sku"])
        acc[k] = acc.get(k, 0) + it["quantity"]
    return [{"product_id": p, "sku": s, "quantity": q} for (p, s), q in acc.items()]


def _mark(order_code, sku):
    return f"{order_code}|{sku}"


async def _restore_one(db, pid, sku, qty):
    await db.products.update_one(
        {"id": pid, "variants.sku": sku},
        {"$inc": {"variants.$.stock": qty}},
    )


async def restore(db, items):
    """LEGACY (order tanpa penanda): kembalikan stok. Pemanggil wajib menjaga agar hanya sekali."""
    for it in _norm(items):
        await _restore_one(db, it["product_id"], it["sku"], it["quantity"])


async def release(db, order_code, items):
    """Kembalikan stok reservasi order. Idempoten per baris (hanya bila penanda masih ada)."""
    for it in _merged(items):
        m = _mark(order_code, it["sku"])
        await db.products.update_one(
            {"id": it["product_id"], "stock_holds": m, "variants.sku": it["sku"]},
            {"$inc": {"variants.$.stock": it["quantity"]}, "$pull": {"stock_holds": m}},
        )


async def commit(db, order_code, items):
    """Order selesai: stok memang terpakai → buang penanda (stok tak berubah)."""
    for it in _merged(items):
        await db.products.update_one({"id": it["product_id"]},
                                     {"$pull": {"stock_holds": _mark(order_code, it["sku"])}})


async def reserve(db, order_code, items):
    """Kurangi stok ATOMIK per SKU dengan penanda order. Return (ok, failed_item).
    Satu baris gagal (stok kurang) → semua baris order ini dilepas (release idempoten)."""
    for it in _merged(items):
        pid, sku, qty = it["product_id"], it["sku"], it["quantity"]
        m = _mark(order_code, sku)
        res = await db.products.update_one(
            {"id": pid, "stock_holds": {"$ne": m},
             "variants": {"$elemMatch": {"sku": sku, "stock": {"$gte": qty}}}},
            {"$inc": {"variants.$.stock": -qty}, "$push": {"stock_holds": m}},
        )
        if res.modified_count != 1 and not await db.products.count_documents({"id": pid, "stock_holds": m}):
            await release(db, order_code, items)
            return False, it
    return True, None


class _Short(Exception):
    def __init__(self, item):
        self.item = item


async def decrement(db, items):
    """Kurangi stok tanpa penanda (dipakai forensik/uji lama). Semua-atau-tidak."""
    applied = []
    try:
        for it in _norm(items):
            res = await db.products.update_one(
                {"id": it["product_id"], "variants": {"$elemMatch": {"sku": it["sku"], "stock": {"$gte": it["quantity"]}}}},
                {"$inc": {"variants.$.stock": -it["quantity"]}},
            )
            if res.modified_count != 1:
                raise _Short(it)
            applied.append(it)
    except BaseException as e:  # stok kurang ATAU write melempar → pulihkan yang sudah turun
        for done in applied:
            await _restore_one(db, done["product_id"], done["sku"], done["quantity"])
        if isinstance(e, _Short):
            return False, e.item
        raise
    return True, None


async def available_stock(db, product_id, sku):
    """Stok tersedia untuk 1 SKU (untuk pesan error yang jujur). None bila tak ada."""
    if not sku:
        return None
    doc = await db.products.find_one(
        {"id": product_id, "variants.sku": sku}, {"variants": 1, "_id": 0})
    if not doc:
        return None
    for v in doc.get("variants", []):
        if v.get("sku") == sku:
            return max(0, int(v.get("stock", 0) or 0))
    return None


__all__ = ["reserve", "release", "commit", "decrement", "restore", "available_stock", "money"]
