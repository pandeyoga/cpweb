"""services/media_maint.py — Migrasi legacy, penulisan ulang referensi URL, lokalisasi aset eksternal. (dipecah dari services/media.py; API publik via services.media)."""
from core_utils import now_iso
from services.audit import log_action
from services.media_core import (
    MediaError,
    _mirror_put,
    _slug_name,
    guess_mime_from_name,
    is_remote_url,
    safe_rel_path,
)
from services.media_ingest import ingest_url


async def migrate_legacy(db, actor_id: str = "system"):
    """Idempotent: rapikan dokumen media lama agar cocok kontrak baru.

    - `created_at` -> `uploaded_at` bila belum ada (sort konsisten).
    - `filename` diisi dari original_name / URL.
    - `stored_path` diisi untuk berkas datar lama `media/<uuid>.<ext>`.
    - `thumb_url`/`medium_url` fallback ke url.
    - `source` diberi label upload/external.
    """
    n = 0
    docs = await db.media_assets.find({}, {"_id": 0}).to_list(5000)
    for d in docs:
        patch = {}
        if not d.get("uploaded_at"):
            patch["uploaded_at"] = d.get("created_at") or now_iso()
        if not d.get("created_at"):
            patch["created_at"] = d.get("uploaded_at") or now_iso()
        if not d.get("updated_at"):
            patch["updated_at"] = patch.get("uploaded_at") or d.get("uploaded_at") or now_iso()
        url = d.get("url") or ""
        if not d.get("filename"):
            patch["filename"] = _slug_name(
                d.get("original_name") or url.split("?")[0].rsplit("/", 1)[-1], "gambar"
            )
        if "folder_id" not in d:
            patch["folder_id"] = None
        if not d.get("stored_path") and url.startswith("/api/media/"):
            rel = url[len("/api/media/"):]
            p = safe_rel_path(rel)
            if p is not None:
                patch["stored_path"] = rel
                if p.exists():
                    try:
                        patch["size"] = d.get("size") or p.stat().st_size
                    except Exception:  # best-effort: kegagalan sekunder media tak boleh memblokir alur utama
                        pass
                    # Mirror berkas lama agar ikut terlindungi self-heal.
                    try:
                        with open(p, "rb") as f:
                            await _mirror_put(db, rel, f.read(),
                                              guess_mime_from_name(p.name))
                    except Exception:  # best-effort: kegagalan sekunder media tak boleh memblokir alur utama
                        pass
        if not d.get("thumb_url"):
            patch["thumb_url"] = url
        if not d.get("medium_url"):
            patch["medium_url"] = url
        if not d.get("source"):
            patch["source"] = "upload" if url.startswith("/api/media/") else "external"
        if not d.get("kind"):
            patch["kind"] = "image"
        if patch:
            await db.media_assets.update_one({"id": d["id"]}, {"$set": patch})
            n += 1
    return {"migrated": n, "total": len(docs)}


def _deep_replace(value, old: str, new: str):
    """Ganti string `old` -> `new` secara rekursif di dict/list/str. Kembalikan (nilai, n)."""
    if isinstance(value, str):
        return (new, 1) if value == old else (value, 0)
    if isinstance(value, list):
        total = 0
        out = []
        for v in value:
            nv, n = _deep_replace(v, old, new)
            out.append(nv)
            total += n
        return out, total
    if isinstance(value, dict):
        total = 0
        out = {}
        for k, v in value.items():
            nv, n = _deep_replace(v, old, new)
            out[k] = nv
            total += n
        return out, total
    return value, 0


async def rewrite_references(db, old_url: str, new_url: str) -> int:
    """Perbarui SEMUA tempat yang memakai `old_url` menjadi `new_url`.

    Cakupan: galeri produk, gambar kategori, foto lokasi toko, logo/QR metode bayar,
    OG image di settings, dan seluruh section CMS (`content.data`, nested).
    """
    n = 0
    # Produk (array images)
    cur = db.products.find({"images": old_url}, {"_id": 0, "id": 1, "images": 1})
    async for p in cur:
        imgs = [new_url if u == old_url else u for u in (p.get("images") or [])]
        await db.products.update_one({"id": p["id"]},
                                     {"$set": {"images": imgs, "updated_at": now_iso()}})
        n += 1
    # Field tunggal
    for coll, field in (("categories", "image"), ("occasions", "image"),
                        ("characters", "image"), ("store_locations", "photo"),
                        ("payment_methods", "logo"), ("payment_methods", "qr_image")):
        res = await db[coll].update_many({field: old_url}, {"$set": {field: new_url}})
        n += int(res.modified_count or 0)
    # Settings singleton
    res = await db.settings.update_many({"og_image": old_url}, {"$set": {"og_image": new_url}})
    n += int(res.modified_count or 0)
    # CMS content (data nested bebas)
    cur = db.content.find({}, {"_id": 0, "id": 1, "key": 1, "data": 1})
    async for c in cur:
        data, cnt = _deep_replace(c.get("data"), old_url, new_url)
        if cnt:
            await db.content.update_one({"id": c["id"]},
                                        {"$set": {"data": data, "updated_at": now_iso()}})
            n += cnt
    return n


async def localize_external(db, actor_id: str, limit: int = 300):
    """Unduh SEMUA aset ber-URL eksternal ke disk lokal + perbarui referensinya.

    Ini pagar utama terhadap \"broken image\": gambar yang tadinya hanya di-hotlink ke
    situs luar (bisa mati / memblokir) menjadi berkas milik sendiri.
    """
    docs = await db.media_assets.find(
        {"$or": [{"source": "external"},
                 {"stored_path": {"$in": [None, ""]}},
                 {"stored_path": {"$exists": False}}]},
        {"_id": 0},
    ).to_list(limit)
    out = {"converted": 0, "failed": [], "refs_updated": 0, "details": []}
    for d in docs:
        old_url = (d.get("url") or "").strip()
        if not is_remote_url(old_url):
            continue
        try:
            fresh = await ingest_url(db, old_url, actor_id, folder_id=d.get("folder_id"),
                                     alt=d.get("alt"), title=d.get("title"))
        except MediaError as e:
            out["failed"].append({"url": old_url[:120], "error": str(e)})
            continue
        except Exception as e:  # noqa: BLE001
            out["failed"].append({"url": old_url[:120], "error": f"{type(e).__name__}"})
            continue
        refs = await rewrite_references(db, old_url, fresh["url"])
        out["refs_updated"] += refs
        out["converted"] += 1
        out["details"].append({"from": old_url[:120], "to": fresh["url"], "refs": refs})
        if d.get("id") != fresh.get("id"):
            await db.media_assets.delete_one({"id": d["id"]})
    await log_action(actor_id, "update", "media_assets", "localize",
                     {"converted": out["converted"], "refs": out["refs_updated"]})
    return out


async def count_external(db) -> int:
    return await db.media_assets.count_documents({
        "$or": [{"source": "external"},
                {"stored_path": {"$in": [None, ""]}},
                {"stored_path": {"$exists": False}}],
        "url": {"$regex": "^https?://"},
    })
