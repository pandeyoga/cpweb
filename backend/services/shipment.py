"""services/shipment.py — pengiriman: kurir + nomor resi + email "Pesanan Dikirim" (E16).

- ship_order(): status `shipped` dari admin WAJIB lewat sini (resi wajib) → transition_order (SSOT) →
  simpan `orders.shipment` → email ke pembeli.
- update_shipment(): koreksi resi/kurir saat masih `shipped` → email ulang OTOMATIS (dedupe per
  kurir+resi di notify, jadi simpan ulang tanpa perubahan tidak mengirim dobel).
Halaman lacak resmi kurir berbasis form (tanpa deep link) → email menonjolkan resi untuk disalin;
kurir tak dikenal → cekresi.com dengan resi terisi.
"""
import re
from urllib.parse import quote

from core_utils import now_iso, safe_doc
from external_urls import COURIER_FALLBACK_URL as FALLBACK_URL
from external_urls import COURIER_TRACK_URLS as URLS
from services import notify
from services import orders as orders_svc

COURIERS = [
    {"id": "jne", "name": "JNE", "url": URLS["jne"], "keywords": ["jne"]},
    {"id": "jnt", "name": "J&T Express", "url": URLS["jnt"], "keywords": ["jnt", "j&t"]},
    {"id": "sicepat", "name": "SiCepat", "url": URLS["sicepat"], "keywords": ["sicepat"]},
    {"id": "anteraja", "name": "AnterAja", "url": URLS["anteraja"], "keywords": ["anteraja"]},
    {"id": "lainnya", "name": "Kurir lain", "url": None, "keywords": []},
]
_RESI = re.compile(r"^[A-Za-z0-9-]{6,40}$")


class ShipmentError(Exception):
    """400 — input pengiriman tidak valid."""


def _build(courier, tracking_number):
    resi = re.sub(r"\s+", "", tracking_number or "")
    if not _RESI.match(resi):
        raise ShipmentError("Nomor resi wajib diisi (6–40 karakter huruf/angka)")
    c = next((x for x in COURIERS if x["id"] == courier), None)
    if not c:
        raise ShipmentError("Pilih kurir pengiriman")
    url = c["url"] or FALLBACK_URL.format(resi=quote(resi))
    return {"courier": c["id"], "courier_name": c["name"], "tracking_number": resi, "tracking_url": url}


async def ship_order(db, order, courier, tracking_number):
    shipment = _build(courier, tracking_number)  # validasi DULU, baru ubah status
    shipment["shipped_at"] = now_iso()
    # status `shipped` + resi dalam SATU update ber-CAS (butir 4) — tak ada `shipped` tanpa resi.
    result = await orders_svc.transition_order(db, order, "shipped", reason="admin", extra={"shipment": shipment})
    notify.shipped_async(db, order["code"])
    result["shipment"] = shipment
    return result


async def update_shipment(db, order, courier, tracking_number):
    if order.get("status") != "shipped":
        raise ShipmentError("Resi hanya bisa diubah saat pesanan berstatus Dikirim")
    shipment = {**(order.get("shipment") or {}), **_build(courier, tracking_number)}
    shipment.setdefault("shipped_at", now_iso())
    res = await db.orders.update_one({"code": order["code"], "status": "shipped"},
                                     {"$set": {"shipment": shipment, "updated_at": now_iso()}})
    if res.modified_count or res.matched_count:
        notify.shipped_async(db, order["code"])
    return safe_doc(await db.orders.find_one({"code": order["code"]}))
