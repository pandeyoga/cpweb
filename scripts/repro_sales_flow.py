"""Repro/regresi bug alur penjualan (audit Midtrans-prep). Jalankan: python scripts/repro_sales_flow.py"""
import asyncio
import os
import sys

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
API = os.environ.get("API_BASE", "http://localhost:8001") + "/api"
RES = []


def check(name, ok, info=""):
    RES.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f" — {info}" if info else ""))


async def login(c, email, pw):
    r = await c.post(f"{API}/auth/login", json={"email": email, "password": pw})
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def pick_variant(db):
    p = await db.products.find_one({"status": "active", "variants.0": {"$exists": True}})
    v = p["variants"][0]
    await db.products.update_one({"id": p["id"], "variants.sku": v["sku"]}, {"$set": {"variants.$.stock": 50}})
    return p["id"], v["sku"]


async def stock_of(db, pid, sku):
    p = await db.products.find_one({"id": pid})
    return next(v["stock"] for v in p["variants"] if v["sku"] == sku)


def body(pid, sku, qty=1, email="tamu@example.com"):
    return {"items": [{"product_id": pid, "sku": sku, "quantity": qty}],
            "address": {"name": "Tamu", "phone": "0812", "street": "Jl A", "city": "Bandung",
                        "province": "Jabar", "email": email},
            "shipping_id": "jne-reg", "payment": {"group": "transfer", "method_id": "bca"},
            "email": email}


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await db.payment_methods.update_one({"id": "bca"}, {"$set": {"active": True}})  # uji alur bukti manual (legacy)
    async with httpx.AsyncClient(timeout=30) as c:
        adm = await login(c, "admin@collectorparfum.id", "Admin#2026")
        cus = await login(c, "customer@collectorparfum.id", "Customer#2026")
        pid, sku = await pick_variant(db)

        # BUG-SALES-01: order tamu bisa dibaca siapa pun hanya dgn kode berurutan (PII bocor).
        r = await c.post(f"{API}/orders", json=body(pid, sku))
        guest = r.json()
        r2 = await c.get(f"{API}/orders/{guest['code']}")
        check("guest order tanpa token akses → 404", r2.status_code == 404, f"got {r2.status_code}")
        tok = guest.get("access_token")
        r3 = await c.get(f"{API}/orders/{guest['code']}", params={"t": tok or "x"})
        check("guest order dgn access_token → 200", r3.status_code == 200, f"got {r3.status_code}")

        # BUG-SALES-02: cancel paralel → stok dikembalikan berkali-kali.
        r = await c.post(f"{API}/orders", json=body(pid, sku, 2), headers=cus)
        code = r.json()["code"]
        before = await stock_of(db, pid, sku)
        await asyncio.gather(*[c.put(f"{API}/admin/orders/{code}/status", json={"status": "cancelled"},
                                     headers=adm) for _ in range(5)])
        after = await stock_of(db, pid, sku)
        check("cancel paralel mengembalikan stok tepat sekali", after - before == 2, f"delta={after - before}")

        # BUG-SALES-03: admin set pending→paid tanpa pembayaran → status/payment_status tak konsisten.
        r = await c.post(f"{API}/orders", json=body(pid, sku), headers=cus)
        code = r.json()["code"]
        r = await c.put(f"{API}/admin/orders/{code}/status", json={"status": "paid"}, headers=adm)
        check("pending→paid manual tanpa pembayaran ditolak", r.status_code == 400, f"got {r.status_code}")
        await c.post(f"{API}/orders/{code}/cancel", headers=cus)

        # BUG-SALES-04: bukti bayar melebihi sisa tagihan.
        r = await c.post(f"{API}/orders", json=body(pid, sku), headers=cus)
        o = r.json()
        r = await c.post(f"{API}/orders/{o['code']}/payment-proof", json={"amount": o["total"] * 10}, headers=cus)
        check("bukti > sisa tagihan ditolak", r.status_code == 400, f"got {r.status_code}")
        await c.post(f"{API}/orders/{o['code']}/cancel", headers=cus)

        # BUG-SALES-05: pembatalan pelanggan pada order yang sudah dibayar/dikemas.
        r = await c.post(f"{API}/orders", json=body(pid, sku), headers=cus)
        o = r.json()
        r = await c.post(f"{API}/orders/{o['code']}/payment-proof", json={"amount": o["total"]}, headers=cus)
        pr = r.json()
        await c.put(f"{API}/admin/payments/{pr['id']}/verify", json={"approve": True}, headers=adm)
        r = await c.post(f"{API}/orders/{o['code']}/cancel", headers=cus)
        check("pelanggan tak bisa batalkan order lunas", r.status_code == 400, f"got {r.status_code}")
        # bersihkan order lunas uji (admin-cancel order lunas melanggar INV-P2 → SALES-16)
        paid_o = await db.orders.find_one({"code": o["code"]})
        from services import stock
        await stock.restore(db, paid_o.get("items", []))
        await db.payment_proofs.delete_many({"order_code": o["code"]})
        await db.orders.delete_one({"code": o["code"]})
        await db.analytics_events.delete_many({"order_code": o["code"]})
        await db.analytics_events.delete_many({"order_code": o["code"]})

    from services.gateway import sync_payment_methods
    await sync_payment_methods(db)
    print(f"\n{sum(RES)}/{len(RES)} PASS")
    sys.exit(0 if all(RES) else 1)


asyncio.run(main())
