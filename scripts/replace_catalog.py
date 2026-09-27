#!/usr/bin/env python3
"""replace_catalog.py — GANTI SELURUH katalog produk dari file Excel (jalankan di VPS kapan saja).

Sumber data (bisa Anda edit lalu jalankan ulang):
  imports/catalog/produk.xlsx       sheet "Produk": 1 baris = 1 varian (Ukuran × Tipe)
  imports/catalog/harga_matrix.csv  harga/harga coret/stok per tier × ukuran × tipe
    (harga/stok per baris di Excel bila > 0 MENANG atas matriks)

Aturan:
  - Validasi dulu. Ada error → berhenti, tidak ada data yang diubah.
  - Produk hanya "active" bila SEMUA variannya punya harga > 0 (tidak ada harga fiktif);
    selain itu disimpan "archived" (tidak tampil di toko) sampai harga diisi.
  - --apply: backup server otomatis (Admin › Backup) → produk slug sama DIGANTI (id lama dipertahankan
    agar riwayat pesanan tetap valid) → produk baru ditambah → produk lama yang tidak ada di file
    DIHAPUS, kecuali yang pernah dipesan (diarsipkan agar pesanan lama tidak rusak).
  - Field: tier (CP01/CP02/CP03/EXCLUSIVE), day_night (Day / Night / Day/Night / kosong).
    Kolom lama date_night (TRUE) tetap diterima → Day/Night. concentration & ingredients tidak diisi.
  - Harga/stok yang SUDAH ADA di database (SKU sama, atau slug+Ukuran+Tipe sama) DIPERTAHANKAN bila
    baris Excel kosong/0 (prioritas: Excel > database > harga_matrix.csv). --no-keep-prices mematikannya.

Usage (dari folder aplikasi, mis. /home/collector/collector-parfum):
  python3 scripts/replace_catalog.py                 # cek/validasi saja (aman)
  python3 scripts/replace_catalog.py --apply         # backup + ganti katalog
  Opsi: --file X.xlsx  --prices X.csv  --no-keep-prices  --archive-out-of-stock
"""
import argparse
import asyncio
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "backend" / ".env")
import os  # noqa: E402

import openpyxl  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from core_utils import DAY_NIGHT_LABEL, new_id, normalize_day_night, now_iso  # noqa: E402
from services import backup as backup_svc  # noqa: E402
from services import variants as V  # noqa: E402

SIZES = ["35ml", "60ml", "100ml"]
TYPES = ["Basic", "Refine", "Intense"]
TIERS = ["CP01", "CP02", "CP03", "EXCLUSIVE"]
GENDERS = {"Pria", "Wanita", "Unisex"}
REQUIRED = ["slug", "name", "category", "gender", "tier", "option1_name", "option1_value",
            "option2_name", "option2_value"]
PRODUCT_FIELDS = ["name", "brand", "category", "gender", "description", "tags", "tier", "day_night",
                  "characters", "best_seller", "is_new", "status", "images", "video_url"]
# Karakter hasil scraping rusak (diketahui) → keluarga aroma dari notes-nya; dilaporkan sebagai PERINGATAN.
JUNK_CHARACTERS = {"bold-and-sensual", "excellent-choice-to-present-the-new", "new"}
CHARACTER_FIX = {
    "burberry-her-elixir-w": "floral-fruity-gourmand", "hugo-boss-element-m": "aromatic-aquatic",
    "victoria-s-secret-pink-fruity-w": "gourmand", "tiziana-terenzi-kirke-overdose-u": "floral-fruity-gourmand",
    "parfums-de-marly-valaya-exclusif-w": "floral-woody-musk",
}
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DEFAULT_FILE = ROOT / "imports" / "catalog" / "produk.xlsx"
DEFAULT_PRICES = ROOT / "imports" / "catalog" / "harga_matrix.csv"
REPORT = ROOT / "imports" / "catalog" / "laporan_terakhir.json"


def truthy(v):
    return v is True or str(v).strip().lower() in ("true", "1", "ya", "yes")


def as_int(v):
    if v in (None, ""):
        return 0
    try:
        return int(float(str(v).replace(".", "").replace(",", "")) if isinstance(v, str) else float(v))
    except ValueError:
        raise ValueError(f"angka tidak valid: {v!r}")


def split_list(v):
    return [x.strip() for x in str(v or "").split(",") if x.strip()]


def load_rows(path):
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)["Produk"]
    it = ws.iter_rows(values_only=True)
    hdr = [str(h).strip() if h else None for h in next(it)]
    missing = [c for c in REQUIRED if c not in hdr]
    if missing:
        raise SystemExit(f"Kolom wajib tidak ada di sheet Produk: {missing}")
    legacy_dn = "day_night" not in hdr and "date_night" in hdr
    rows = []
    for n, r in enumerate(it, start=2):
        if any(c not in (None, "") for c in r):
            d = {h: v for h, v in zip(hdr, r) if h}
            if legacy_dn:
                d["day_night"] = "both" if truthy(d.pop("date_night", None)) else ""
            rows.append((n, d))
    return rows


def load_prices(path, errors):
    out = {}
    if not Path(path).exists():
        return out
    with open(path, newline="", encoding="utf-8-sig") as f:
        for n, r in enumerate(csv.DictReader(f), start=2):
            key = (r.get("tier", "").strip(), r.get("ukuran", "").strip(), r.get("tipe", "").strip())
            try:
                price, cap, stock = as_int(r.get("harga")), as_int(r.get("harga_coret")), as_int(r.get("stok"))
            except ValueError as e:
                errors.append(f"harga_matrix.csv baris {n}: {e}")
                continue
            if key[0] not in TIERS or key[1] not in SIZES or key[2] not in TYPES:
                errors.append(f"harga_matrix.csv baris {n}: kombinasi tidak dikenal {key}")
            elif min(price, cap, stock) < 0 or (cap and cap <= price):
                errors.append(f"harga_matrix.csv baris {n}: harga/stok negatif atau harga_coret <= harga")
            else:
                out[key] = (price, cap, stock)
    return out


def validate(rows, categories):
    errors, warns = [], []
    groups, skus = defaultdict(list), Counter()
    for n, r in rows:
        e = []
        slug = str(r.get("slug") or "").strip()
        if not SLUG_RE.match(slug):
            e.append(f"slug tidak valid {slug!r}")
        if r.get("category") not in categories:
            e.append(f"kategori {r.get('category')!r} tidak ada")
        if r.get("gender") not in GENDERS:
            e.append(f"gender {r.get('gender')!r} (harus Pria/Wanita/Unisex)")
        if r.get("tier") not in TIERS:
            e.append(f"tier {r.get('tier')!r} (harus {'/'.join(TIERS)})")
        if r.get("option1_name") != "Ukuran" or r.get("option1_value") not in SIZES:
            e.append(f"Ukuran {r.get('option1_value')!r} (harus {'/'.join(SIZES)})")
        if r.get("option2_name") != "Tipe" or r.get("option2_value") not in TYPES:
            e.append(f"Tipe {r.get('option2_value')!r} (harus {'/'.join(TYPES)})")
        dn = r.get("day_night")
        if dn not in (None, "") and not normalize_day_night(dn):
            e.append(f"day_night {dn!r} (harus Day / Night / Day/Night / kosong)")
        for c in split_list(r.get("characters")):
            if not SLUG_RE.match(c):
                e.append(f"characters {c!r} bukan slug")
        try:
            as_int(r.get("variant_price")), as_int(r.get("variant_stock"))
        except ValueError as ex:
            e.append(str(ex))
        if r.get("variant_sku"):
            skus[str(r["variant_sku"]).strip()] += 1
        errors += [f"baris {n}: {x}" for x in e]
        groups[slug].append((n, r))
    for slug, rs in groups.items():
        junk = JUNK_CHARACTERS & set(split_list(rs[0][1].get("characters")))
        if junk:
            warns.append(f"produk {slug}: karakter rusak {sorted(junk)} → {clean_characters(slug, rs[0][1].get('characters'))}"
                         " (otomatis; cek manual)")
    errors += [f"SKU duplikat: {s}" for s, c in skus.items() if c > 1]
    for slug, rs in groups.items():
        for f in PRODUCT_FIELDS:
            vals = {str(r.get(f)) for _, r in rs}
            if len(vals) > 1:
                errors.append(f"produk {slug}: kolom {f} berbeda antar baris ({', '.join(sorted(vals))[:120]})")
        combos = Counter((r.get("option1_value"), r.get("option2_value")) for _, r in rs)
        errors += [f"produk {slug}: varian duplikat {c}" for c, k in combos.items() if k > 1]
        if len(combos) != len(SIZES) * len(TYPES):
            warns.append(f"produk {slug}: {len(combos)} varian (standar 9)")
    return groups, errors, warns


def clean_characters(slug, raw):
    chars = split_list(raw)
    if not JUNK_CHARACTERS & set(chars):
        return chars
    fixed = [c for c in chars if c not in JUNK_CHARACTERS]
    return fixed or split_list(CHARACTER_FIX.get(slug, ""))


async def load_existing_prices(db):
    """Harga/stok varian yang sudah ada di DB → {sku: (...)} dan {(slug, ukuran, tipe): (...)}."""
    by_sku, by_combo = {}, {}
    async for p in db.products.find({}, {"_id": 0, "slug": 1, "variants": 1}):
        for v in p.get("variants") or []:
            val = (int(v.get("price") or 0), int(v.get("compare_at_price") or 0), int(v.get("stock") or 0))
            if val[0] <= 0:
                continue
            if v.get("sku"):
                by_sku[str(v["sku"]).strip().upper()] = val
            o = v.get("options") or {}
            by_combo[(p.get("slug"), o.get("Ukuran"), o.get("Tipe"))] = val
    return by_sku, by_combo


def build_doc(slug, rs, prices, archive_oos, now, existing=({}, {})):
    head = rs[0][1]
    variants, from_db = [], 0
    for _, r in sorted(rs, key=lambda x: (SIZES.index(x[1]["option1_value"]), TYPES.index(x[1]["option2_value"]))):
        size, typ = r["option1_value"], r["option2_value"]
        sku = str(r.get("variant_sku") or f"{slug.upper()}-{typ.upper()}-{size.upper()}").strip()
        mp, mcap, mstock = prices.get((head["tier"], size, typ), (0, 0, 0))
        ex = existing[0].get(sku.upper()) or existing[1].get((slug, size, typ))
        price = as_int(r.get("variant_price")) or (ex[0] if ex else 0) or mp
        cap = as_int(r.get("variant_compare_at_price")) or (ex[1] if ex else 0) or mcap
        stock = as_int(r.get("variant_stock")) or (ex[2] if ex else 0) or mstock
        from_db += bool(ex and not as_int(r.get("variant_price")))
        variants.append({
            "sku": sku, "options": {"Ukuran": size, "Tipe": typ}, "price": price, "stock": stock,
            "compare_at_price": cap if cap > price else None,
        })
    options = [{"name": "Ukuran", "values": [s for s in SIZES if any(v["options"]["Ukuran"] == s for v in variants)]},
               {"name": "Tipe", "values": [t for t in TYPES if any(v["options"]["Tipe"] == t for v in variants)]}]
    priced = all(v["price"] > 0 for v in variants)
    in_stock = any(v["stock"] > 0 for v in variants)
    wanted = str(head.get("status") or "active").strip().lower()
    status = "active" if wanted == "active" and priced and (in_stock or not archive_oos) else "archived"
    return {
        "id": new_id("prd"), "slug": slug, "name": str(head["name"]).strip(),
        "brand": str(head.get("brand") or "Collector Parfum").strip(), "category": head["category"],
        "gender": head["gender"], "tier": head["tier"], "day_night": normalize_day_night(head.get("day_night")),
        "description": str(head.get("description") or "").strip(),
        "tags": split_list(head.get("tags")), "characters": clean_characters(slug, head.get("characters")),
        "occasions": [],
        "best_seller": truthy(head.get("best_seller")), "is_new": truthy(head.get("is_new")),
        "images": split_list(head.get("images")), "video_url": head.get("video_url") or None,
        "options": options, "variants": variants, "volumes": V.derive_volumes(options, variants),
        **V.price_range(variants),
        "notes": {"top": [], "heart": [], "base": []}, "performance": {}, "seo": {},
        "status": status, "rating_avg": 0.0, "rating_count": 0, "created_at": now, "updated_at": now,
        "_priced_from_db": from_db,
    }


async def ensure_taxonomy(db, docs, keep_occasions):
    have = set(await db.characters.distinct("slug"))
    new = sorted({c for d in docs for c in d["characters"]} - have)
    base = await db.characters.count_documents({})
    for i, slug in enumerate(new):
        await db.characters.insert_one({"id": new_id("chr"), "slug": slug, "name": slug.replace("-", " ").title(),
                                        "desc": "", "icon": "sparkles", "active": True, "order": base + i + 1,
                                        "created_at": now_iso()})
    hidden = 0
    if not keep_occasions:  # facet momen kini = day_night; occasion lama disembunyikan
        hidden = (await db.occasions.update_many({}, {"$set": {"active": False}})).modified_count
    return new, hidden


async def apply(db, docs, keep_occasions):
    try:
        bkp = await backup_svc.create_server_backup(
            db, ["products", "characters", "occasions", "wishlists", "carts"], "replace-catalog",
            note="Otomatis sebelum replace_catalog.py")
        print(f"  Backup dibuat: {bkp['id']} ({bkp['size']:,} byte) — pulihkan via Admin › Backup bila perlu")
    except ValueError as e:
        print(f"  (backup dilewati: {e})")
    new_chars, hidden = await ensure_taxonomy(db, docs, keep_occasions)
    old = {p["slug"]: p async for p in db.products.find({}, {"id": 1, "slug": 1, "created_at": 1,
                                                                "rating_avg": 1, "rating_count": 1})}
    ordered = set(await db.orders.distinct("items.product_id"))
    replaced, inserts = 0, []
    for d in docs:
        o = old.get(d["slug"])
        if o:
            d.update(id=o["id"], created_at=o.get("created_at") or d["created_at"],
                     rating_avg=o.get("rating_avg", 0.0), rating_count=o.get("rating_count", 0))
            await db.products.replace_one({"id": o["id"]}, d)
            replaced += 1
        else:
            inserts.append(d)
    for i in range(0, len(inserts), 500):
        await db.products.insert_many([dict(x) for x in inserts[i:i + 500]])
    keep = {d["slug"] for d in docs}
    stale = [p for s, p in old.items() if s not in keep]
    arch = [p["id"] for p in stale if p["id"] in ordered]
    dele = [p["id"] for p in stale if p["id"] not in ordered]
    if arch:
        await db.products.update_many({"id": {"$in": arch}}, {"$set": {"status": "archived", "updated_at": now_iso()}})
    if dele:
        await db.products.delete_many({"id": {"$in": dele}})
        await db.wishlists.update_many({}, {"$pull": {"product_ids": {"$in": dele}}})
        await db.carts.update_many({}, {"$pull": {"items": {"product_id": {"$in": dele}}}})
    return {"replaced": replaced, "inserted": len(inserts), "deleted_old": len(dele),
            "archived_old_ordered": len(arch), "new_characters": new_chars, "occasions_hidden": hidden}


async def main():
    ap = argparse.ArgumentParser(description="Ganti seluruh katalog produk dari Excel.")
    ap.add_argument("--file", default=str(DEFAULT_FILE))
    ap.add_argument("--prices", default=str(DEFAULT_PRICES))
    ap.add_argument("--apply", action="store_true", help="tulis ke database (tanpa ini = cek saja)")
    ap.add_argument("--keep-occasions", action="store_true", help="jangan sembunyikan occasion lama")
    ap.add_argument("--no-keep-prices", action="store_true",
                    help="JANGAN pakai harga/stok lama dari database (default: dipakai bila Excel kosong)")
    ap.add_argument("--archive-out-of-stock", action="store_true", help="arsipkan produk yang semua stoknya 0")
    ap.add_argument("--allow-empty-store", action="store_true",
                    help="izinkan --apply walau belum ada produk berharga (semua jadi archived, toko kosong)")
    a = ap.parse_args()
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    print(f"Database: {os.environ['DB_NAME']} | file: {a.file}")
    rows = load_rows(a.file)
    categories = set(await db.categories.distinct("slug"))
    groups, errors, warns = validate(rows, categories)
    prices = load_prices(a.prices, errors)
    now = now_iso()
    existing = ({}, {}) if a.no_keep_prices else await load_existing_prices(db)
    docs = [] if errors else [build_doc(s, rs, prices, a.archive_out_of_stock, now, existing)
                              for s, rs in groups.items()]
    priced_db = [d.pop("_priced_from_db") for d in docs]
    summary = {
        "rows": len(rows), "products": len(groups), "errors": len(errors), "warnings": len(warns),
        "price_matrix_filled": f"{sum(1 for v in prices.values() if v[0] > 0)}/36",
        "active": sum(d["status"] == "active" for d in docs),
        "archived_no_price_or_stock": sum(d["status"] == "archived" for d in docs),
        "tiers": dict(Counter(d["tier"] for d in docs)),
        "variants_priced_from_existing_db": sum(priced_db),
        "day_night": {DAY_NIGHT_LABEL[k] or "(kosong)": v for k, v in Counter(d["day_night"] for d in docs).items()},
        "brands_active_top12": [b for b, _ in Counter(d["brand"] for d in docs if d["status"] == "active").most_common(12)],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    for m in errors[:40]:
        print("  ERROR", m)
    for m in warns[:10]:
        print("  PERINGATAN", m)
    if errors:
        print(f"\nValidasi GAGAL ({len(errors)} error) — database TIDAK diubah.")
        return 1
    if summary["archived_no_price_or_stock"]:
        print(f"\nCatatan: {summary['archived_no_price_or_stock']} produk akan disimpan ARCHIVED (belum ada harga"
              " valid di Excel / database lama / harga_matrix.csv). Isi harga lewat Admin › Produk › Impor (isi harga per tier)"
              " atau imports/catalog/harga_matrix.csv lalu jalankan ulang.")
    result = {}
    if a.apply and not summary["active"] and not a.allow_empty_store:
        print("\nDIBATALKAN: tidak ada satu pun produk yang akan aktif (harga belum diisi) sehingga toko akan kosong."
              "\nIsi harga_matrix.csv dulu, atau jalankan dengan --allow-empty-store bila memang disengaja.")
        return 2
    if a.apply:
        result = await apply(db, docs, a.keep_occasions)
        print("SELESAI:", json.dumps(result, ensure_ascii=False))
    else:
        print("\nMode cek saja. Tambahkan --apply untuk menulis ke database.")
    REPORT.write_text(json.dumps({"at": now, "applied": a.apply, "summary": summary, "result": result,
                                  "errors": errors, "warnings": warns}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
