"""services/order_holds.py — reservasi stok & kuota voucher per order yang IDEMPOTEN (butir 4/11).

Tanpa transaksi Mongo: tiap efek memakai penanda di dokumen yang sama dengan counter-nya
(`products.stock_holds`, `vouchers.redeemed_orders`, `voucher_user_usage.orders`) sehingga
klaim/lepas bisa diulang kapan saja tanpa dobel. Flag order (`released`, `holds_committed`)
ditulis SETELAH semua langkah selesai → job rekonsiliasi melanjutkan yang terputus.
"""
from core_utils import new_id, now_iso
from services import stock
from services.order_helpers import OrderError, _release_voucher

HOLD_V = 2


async def claim_voucher(db, order):
    """Klaim kuota global + per-user untuk order (idempoten). Raise OrderError bila habis."""
    code, oc, uid = order.get("voucher_code"), order["code"], order.get("user_id")
    if not code:
        return
    res = await db.vouchers.update_one(
        {"code": code, "redeemed_orders": {"$ne": oc}, "$expr": {"$or": [
            {"$eq": [{"$ifNull": ["$usage_limit", 0]}, 0]},
            {"$lt": [{"$ifNull": ["$used_count", 0]}, {"$ifNull": ["$usage_limit", 0]}]}]}},
        {"$inc": {"used_count": 1}, "$push": {"redeemed_orders": oc}})
    if res.modified_count != 1 and not await db.vouchers.count_documents({"code": code, "redeemed_orders": oc}):
        raise OrderError("Kuota voucher telah habis")
    vdoc = await db.vouchers.find_one({"code": code}, {"per_user_limit": 1}) or {}
    limit = int(vdoc.get("per_user_limit", 0) or 0)
    if uid and limit > 0:
        prior = await db.voucher_redemptions.count_documents({"voucher_code": code, "user_id": uid})
        await db.voucher_user_usage.update_one(
            {"voucher_code": code, "user_id": uid},
            {"$setOnInsert": {"voucher_code": code, "user_id": uid, "count": prior, "orders": [],
                              "created_at": now_iso()}}, upsert=True)
        res = await db.voucher_user_usage.update_one(
            {"voucher_code": code, "user_id": uid, "orders": {"$ne": oc}, "count": {"$lt": limit}},
            {"$inc": {"count": 1}, "$push": {"orders": oc}})
        if res.modified_count != 1 and not await db.voucher_user_usage.count_documents(
                {"voucher_code": code, "user_id": uid, "orders": oc}):
            raise OrderError("Batas pemakaian voucher ini sudah tercapai")
    await db.voucher_redemptions.update_one(
        {"order_code": oc},
        {"$setOnInsert": {"id": new_id("vrd"), "voucher_code": code, "user_id": uid, "order_code": oc,
                          "discount": order.get("discount", 0), "created_at": now_iso()}}, upsert=True)


async def release_voucher_marks(db, order):
    code, oc, uid = order.get("voucher_code"), order["code"], order.get("user_id")
    if not code:
        return
    await db.vouchers.update_one({"code": code, "redeemed_orders": oc},
                                 {"$inc": {"used_count": -1}, "$pull": {"redeemed_orders": oc}})
    if uid:
        await db.voucher_user_usage.update_one({"voucher_code": code, "user_id": uid, "orders": oc},
                                               {"$inc": {"count": -1}, "$pull": {"orders": oc}})
    await db.voucher_redemptions.delete_one({"order_code": oc})


async def release_order(db, order):
    """Kompensasi pembatalan: stok + voucher kembali. Aman diulang; `released` = SELESAI."""
    oc = order["code"]
    if order.get("hold_v") == HOLD_V:
        await stock.release(db, oc, order.get("items", []))
        await release_voucher_marks(db, order)
    else:  # order lama tanpa penanda: sekali saja (flag CAS)
        res = await db.orders.update_one({"code": oc, "stock_restored": {"$ne": True}},
                                         {"$set": {"stock_restored": True}})
        if res.modified_count == 1:
            await stock.restore(db, order.get("items", []))
        await _release_voucher(db, order)
    await db.orders.update_one({"code": oc}, {"$set": {"released": True, "voucher_released": True}})


async def commit_holds(db, order):
    """Order selesai: stok/kuota memang terpakai → buang penanda (angka tak berubah)."""
    if order.get("hold_v") != HOLD_V:
        return
    oc = order["code"]
    await stock.commit(db, oc, order.get("items", []))
    if order.get("voucher_code"):
        await db.vouchers.update_one({"code": order["voucher_code"]}, {"$pull": {"redeemed_orders": oc}})
        if order.get("user_id"):
            await db.voucher_user_usage.update_one(
                {"voucher_code": order["voucher_code"], "user_id": order["user_id"]}, {"$pull": {"orders": oc}})
    await db.orders.update_one({"code": oc}, {"$set": {"holds_committed": True}})


async def abort_reservation(db, order):
    """Order `reserving` gagal/terputus: lepas semua efek lalu hapus draf order."""
    await stock.release(db, order["code"], order.get("items", []))
    await release_voucher_marks(db, order)
    await db.orders.delete_one({"code": order["code"], "status": "reserving"})
