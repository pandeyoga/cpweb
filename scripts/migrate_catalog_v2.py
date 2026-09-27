"""migrate_catalog_v2.py — migrasi data produk lama ke kontrak katalog v2 (idempoten).

- date_night  = True bila produk punya occasion "date-night"; occasions → ["date-night"] / [].
- concentration & ingredients DIHAPUS dari dokumen (bukan diubah jadi EDP).
- Varian: dimensi "Konsentrasi" dibuang; Tipe Standard→Basic, Super/Premium→Refine; varian tanpa Tipe → Basic.
  SKU TIDAK diubah (riwayat pesanan & keranjang tetap cocok).
- Occasion selain Date Night dinonaktifkan (tidak jadi SSOT tersembunyi).
- tier TIDAK dikarang: produk tanpa tier dilaporkan agar diisi admin (editor produk / impor).

Usage: python3 scripts/migrate_catalog_v2.py [--apply]
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "backend" / ".env")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from services import variants as V  # noqa: E402

TYPE_MAP = {"Standard": "Basic", "Super": "Refine", "Premium": "Refine"}
DROP_DIMS = {"Konsentrasi", "Concentration"}


def migrate_doc(p):
    options, variants = p.get("options"), p.get("variants")
    if not variants:
        options, variants = V.derive_from_volumes(p)
    has_type = any(o["name"] == "Tipe" for o in options or [])
    new_opts = []
    for o in options or []:
        if o["name"] in DROP_DIMS:
            continue
        vals = [TYPE_MAP.get(v, v) for v in o["values"]] if o["name"] == "Tipe" else list(o["values"])
        new_opts.append({"name": o["name"], "values": list(dict.fromkeys(vals))})
    if not has_type:
        new_opts.insert(0, {"name": "Tipe", "values": ["Basic"]})
    new_vars = []
    for v in variants:
        opts = {k: val for k, val in (v.get("options") or {}).items() if k not in DROP_DIMS}
        opts["Tipe"] = TYPE_MAP.get(opts.get("Tipe"), opts.get("Tipe")) or "Basic"
        new_vars.append({**v, "options": opts})
    dn = bool(p.get("date_night")) or "date-night" in (p.get("occasions") or [])
    return {
        "options": new_opts, "variants": new_vars, "volumes": V.derive_volumes(new_opts, new_vars),
        **V.price_range(new_vars), "date_night": dn, "occasions": ["date-night"] if dn else [],
    }


async def main():
    apply = "--apply" in sys.argv
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    n, no_tier = 0, []
    async for p in db.products.find({}):
        upd = migrate_doc(p)
        if not p.get("tier"):
            no_tier.append(p["slug"])
        n += 1
        if apply:
            await db.products.update_one({"id": p["id"]}, {"$set": upd,
                                                          "$unset": {"concentration": "", "ingredients": ""}})
    hidden = 0
    if apply:
        hidden = (await db.occasions.update_many({"slug": {"$ne": "date-night"}, "active": True},
                                                 {"$set": {"active": False}})).modified_count
    print(f"Produk diproses: {n} | occasion lama dinonaktifkan: {hidden} | tanpa tier: {len(no_tier)}")
    if no_tier:
        print("  Isi tier (CP01/CP02/CP03/EXCLUSIVE) untuk:", ", ".join(no_tier[:30]), "…" if len(no_tier) > 30 else "")
    if not apply:
        print("Mode cek. Tambahkan --apply untuk menulis.")


if __name__ == "__main__":
    asyncio.run(main())
