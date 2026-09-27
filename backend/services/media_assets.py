"""services/media_assets.py — Daftar/ubah/hapus/pindah aset + statistik. (dipecah dari services/media.py; API publik via services.media)."""
import re

from core_utils import now_iso
from services.audit import log_action
from services.media_core import (
    DB_MIRROR,
    HEIF_OK,
    LIST_MAX,
    MAX_MB,
    MEDIA_ROOT,
    MediaError,
    _mirror_delete,
    _slug_name,
    safe_rel_path,
)
from services.media_folders import _descendant_ids, _folder_or_error
from services.media_images import public_asset
from services.media_maint import count_external

SORTS = {
    "newest": [("uploaded_at", -1)],
    "oldest": [("uploaded_at", 1)],
    "name": [("filename", 1)],
    "name_desc": [("filename", -1)],
    "largest": [("size", -1)],
    "smallest": [("size", 1)],
}


def _int(v, default, lo=None, hi=None):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


async def list_assets(db, folder_id="__all__", q=None, kind=None, sort="newest",
                      page=1, limit=48, recursive=False):
    query = {}
    if folder_id != "__all__":
        if folder_id in (None, "", "root"):
            query["folder_id"] = None
        elif recursive:
            ids = await _descendant_ids(db, folder_id)
            query["folder_id"] = {"$in": ids}
        else:
            query["folder_id"] = folder_id
    term = (q or "").strip()
    if term:
        rx = re.compile(re.escape(term), re.I)
        query["$or"] = [{"filename": rx}, {"alt": rx}, {"title": rx},
                        {"original_name": rx}, {"url": rx}]
    if kind in ("image", "video"):
        query["kind"] = kind
    elif kind == "external":
        query["source"] = "external"
    elif kind == "local":
        query["stored_path"] = {"$exists": True, "$ne": None}

    page = _int(page, 1, 1, 10000)
    limit = _int(limit, 48, 1, LIST_MAX)
    order = SORTS.get(sort or "newest", SORTS["newest"])
    total = await db.media_assets.count_documents(query)
    docs = await db.media_assets.find(query, {"_id": 0}).sort(order).skip(
        (page - 1) * limit
    ).limit(limit).to_list(limit)
    return [public_asset(d) for d in docs], total


async def get_asset(db, aid: str):
    doc = await db.media_assets.find_one({"id": aid}, {"_id": 0})
    return public_asset(doc) if doc else None


async def update_asset(db, actor_id: str, aid: str, patch: dict):
    doc = await db.media_assets.find_one({"id": aid}, {"_id": 0})
    if not doc:
        return None
    upd = {"updated_at": now_iso()}
    if "filename" in patch and patch["filename"] is not None:
        name = _slug_name(patch["filename"], "")
        if not name:
            raise MediaError("Nama berkas tidak boleh kosong")
        upd["filename"] = name
    if "alt" in patch:
        upd["alt"] = (str(patch["alt"])[:300] or None) if patch["alt"] is not None else None
    if "title" in patch:
        upd["title"] = (str(patch["title"])[:200] or None) if patch["title"] is not None else None
    if "tags" in patch and patch["tags"] is not None:
        upd["tags"] = [_slug_name(t, "")[:40] for t in list(patch["tags"])[:20] if str(t).strip()]
    if "folder_id" in patch:
        await _folder_or_error(db, patch["folder_id"])
        upd["folder_id"] = patch["folder_id"] or None
    await db.media_assets.update_one({"id": aid}, {"$set": upd})
    await log_action(actor_id, "update", "media_assets", aid, {"fields": list(upd.keys())})
    fresh = await db.media_assets.find_one({"id": aid}, {"_id": 0})
    return public_asset(fresh)


async def _remove_binaries(db, doc: dict):
    rels = []
    for key in ("stored_path",):
        if doc.get(key):
            rels.append(doc[key])
    for key in ("thumb_url", "medium_url"):
        u = doc.get(key) or ""
        if u.startswith("/api/media/"):
            rels.append(u[len("/api/media/"):])
    seen = set()
    for rel in rels:
        if rel in seen:
            continue
        seen.add(rel)
        p = safe_rel_path(rel)
        if p is not None and p.exists():
            try:
                p.unlink()
            except Exception:  # best-effort: kegagalan sekunder media tak boleh memblokir alur utama
                pass
        await _mirror_delete(db, rel)


async def delete_asset(db, actor_id: str, aid: str):
    doc = await db.media_assets.find_one({"id": aid}, {"_id": 0})
    if not doc:
        return None
    # Butir 16: metadata dihapus DULU — bila DB gagal, biner & referensi tetap utuh (tak ada link rusak);
    # biner sisa bila langkah kedua gagal hanya sampah yang tidak direferensikan.
    await db.media_assets.delete_one({"id": aid})
    await _remove_binaries(db, doc)
    await log_action(actor_id, "delete", "media_assets", aid,
                     {"filename": doc.get("filename")})
    return {"deleted": True, "id": aid}


async def bulk_delete(db, actor_id: str, ids):
    ok, fail = [], []
    for aid in list(ids or [])[:500]:
        res = await delete_asset(db, actor_id, aid)
        (ok if res else fail).append(aid)
    return {"deleted": ok, "not_found": fail, "count": len(ok)}


async def bulk_move(db, actor_id: str, ids, folder_id):
    await _folder_or_error(db, folder_id)
    ids = [i for i in list(ids or [])[:500] if i]
    if not ids:
        return {"moved": 0, "folder_id": folder_id or None}
    res = await db.media_assets.update_many(
        {"id": {"$in": ids}},
        {"$set": {"folder_id": folder_id or None, "updated_at": now_iso()}},
    )
    await log_action(actor_id, "update", "media_assets", ",".join(ids[:5]),
                     {"bulk_move": folder_id, "n": res.modified_count})
    return {"moved": int(res.modified_count), "folder_id": folder_id or None}


async def stats(db):
    total = await db.media_assets.count_documents({})
    local = await db.media_assets.count_documents({"stored_path": {"$exists": True, "$ne": None}})
    external = await db.media_assets.count_documents({"source": "external"})
    folders = await db.media_folders.count_documents({})
    size = 0
    try:
        cur = db.media_assets.aggregate([{"$group": {"_id": None, "s": {"$sum": "$size"}}}])
        async for row in cur:
            size = int(row.get("s") or 0)
    except Exception:
        size = 0
    disk = 0
    try:
        for p in MEDIA_ROOT.rglob("*"):
            if p.is_file():
                disk += p.stat().st_size
    except Exception:
        disk = 0
    return {
        "assets": total, "local_assets": local, "external_assets": external,
        "folders": folders, "bytes": size, "disk_bytes": disk,
        "max_mb": MAX_MB, "mirror": DB_MIRROR, "heif": HEIF_OK,
        "media_root": str(MEDIA_ROOT),
        "hotlinked": await count_external(db),
    }


# ============================== legacy compatibility ==============================
async def list_uploads(db, limit: int = 200):
    """Kompatibilitas GET /api/admin/uploads (list datar, terbaru dulu)."""
    docs, _ = await list_assets(db, folder_id="__all__", sort="newest", page=1,
                               limit=min(limit, LIST_MAX))
    return docs
