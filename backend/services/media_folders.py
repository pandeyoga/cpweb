"""services/media_folders.py — Folder bertingkat media (media_folders) + folder default. (dipecah dari services/media.py; API publik via services.media)."""
import re
from typing import Optional

from core_utils import new_id, now_iso
from services.audit import log_action
from services.media_core import ROOT_FOLDER, MediaError, _slug_name


def _folder_doc(d):
    return {
        "id": d.get("id"),
        "name": d.get("name"),
        "parent_id": d.get("parent_id"),
        "path": d.get("path"),
        "depth": int(d.get("depth") or 0),
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
    }


async def list_folders(db):
    docs = await db.media_folders.find({}, {"_id": 0}).sort(
        [("path", 1)]
    ).to_list(1000)
    counts = {}
    try:
        pipeline = [{"$group": {"_id": "$folder_id", "n": {"$sum": 1}}}]
        async for row in db.media_assets.aggregate(pipeline):
            counts[row["_id"]] = int(row["n"])
    except Exception:
        counts = {}
    out = []
    for d in docs:
        f = _folder_doc(d)
        f["asset_count"] = counts.get(f["id"], 0)
        out.append(f)
    root = dict(ROOT_FOLDER)
    root["asset_count"] = counts.get(None, 0)
    root["total_count"] = sum(counts.values())
    return {"root": root, "folders": out}


async def folder_tree(db):
    data = await list_folders(db)
    folders = data["folders"]
    by_parent = {}
    for f in folders:
        by_parent.setdefault(f["parent_id"], []).append(dict(f, children=[]))

    def build(parent_id):
        nodes = by_parent.get(parent_id, [])
        for n in nodes:
            n["children"] = build(n["id"])
            n["total_count"] = n["asset_count"] + sum(c["total_count"] for c in n["children"])
        return sorted(nodes, key=lambda x: (x["name"] or "").lower())

    return {"root": data["root"], "tree": build(None)}


async def _folder_or_error(db, fid):
    if fid in (None, "", "root"):
        return None
    doc = await db.media_folders.find_one({"id": fid}, {"_id": 0})
    if not doc:
        raise MediaError("Folder tidak ditemukan")
    return doc


async def create_folder(db, actor_id: str, name: str, parent_id: Optional[str] = None):
    clean = _slug_name(name, "")
    if not clean:
        raise MediaError("Nama folder wajib diisi")
    parent = await _folder_or_error(db, parent_id)
    pid = parent["id"] if parent else None
    dup = await db.media_folders.find_one(
        {"parent_id": pid, "name": re.compile(f"^{re.escape(clean)}$", re.I)}, {"_id": 1}
    )
    if dup:
        raise MediaError(f"Folder '{clean}' sudah ada di lokasi ini")
    base = (parent["path"].rstrip("/") if parent else "")
    doc = {
        "id": new_id("mdf"),
        "name": clean,
        "parent_id": pid,
        "path": f"{base}/{clean}",
        "depth": (int(parent["depth"]) + 1) if parent else 1,
        "created_by": actor_id,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.media_folders.insert_one(dict(doc))
    await log_action(actor_id, "create", "media_folders", doc["id"], {"name": clean})
    doc.pop("_id", None)
    return dict(_folder_doc(doc), asset_count=0)


async def _reindex_descendants(db, folder_id: str):
    """Hitung ulang path & depth seluruh keturunan (setelah rename/move)."""
    node = await db.media_folders.find_one({"id": folder_id}, {"_id": 0})
    if not node:
        return
    children = await db.media_folders.find({"parent_id": folder_id}, {"_id": 0}).to_list(1000)
    for c in children:
        new_path = f"{node['path'].rstrip('/')}/{c['name']}"
        await db.media_folders.update_one(
            {"id": c["id"]},
            {"$set": {"path": new_path, "depth": int(node["depth"]) + 1, "updated_at": now_iso()}},
        )
        await _reindex_descendants(db, c["id"])


async def update_folder(db, actor_id: str, fid: str, name=None, parent_id="__keep__"):
    node = await db.media_folders.find_one({"id": fid}, {"_id": 0})
    if not node:
        raise MediaError("Folder tidak ditemukan")
    new_name = _slug_name(name, "") if name is not None else node["name"]
    if not new_name:
        raise MediaError("Nama folder wajib diisi")
    new_parent_id = node["parent_id"] if parent_id == "__keep__" else (parent_id or None)
    if new_parent_id == fid:
        raise MediaError("Folder tidak bisa menjadi induk dirinya sendiri")
    parent = await _folder_or_error(db, new_parent_id)
    # Cegah siklus: induk baru tidak boleh keturunan dari fid.
    if parent and (parent["path"] == node["path"] or parent["path"].startswith(node["path"].rstrip("/") + "/")):
        raise MediaError("Tidak bisa memindahkan folder ke dalam turunannya sendiri")
    dup = await db.media_folders.find_one(
        {"parent_id": new_parent_id, "name": re.compile(f"^{re.escape(new_name)}$", re.I),
         "id": {"$ne": fid}},
        {"_id": 1},
    )
    if dup:
        raise MediaError(f"Folder '{new_name}' sudah ada di lokasi tujuan")
    base = (parent["path"].rstrip("/") if parent else "")
    patch = {
        "name": new_name,
        "parent_id": new_parent_id,
        "path": f"{base}/{new_name}",
        "depth": (int(parent["depth"]) + 1) if parent else 1,
        "updated_at": now_iso(),
    }
    await db.media_folders.update_one({"id": fid}, {"$set": patch})
    await _reindex_descendants(db, fid)
    await log_action(actor_id, "update", "media_folders", fid, {"name": new_name})
    fresh = await db.media_folders.find_one({"id": fid}, {"_id": 0})
    return _folder_doc(fresh)


async def delete_folder(db, actor_id: str, fid: str, cascade: bool = False):
    node = await db.media_folders.find_one({"id": fid}, {"_id": 0})
    if not node:
        return None
    subs = await db.media_folders.find({"parent_id": fid}, {"_id": 0}).to_list(1000)
    assets = await db.media_assets.find({"folder_id": fid}, {"_id": 0, "id": 1}).to_list(5000)
    if cascade:
        # Hapus seluruh keturunan + asetnya (rekursif).
        for s in subs:
            await delete_folder(db, actor_id, s["id"], cascade=True)
        for a in assets:
            from services.media_assets import (
                delete_asset,  # lazy: hindari import melingkar
            )
            await delete_asset(db, actor_id, a["id"])
        moved = 0
    else:
        # Aman: pindahkan isi ke induk (tanpa orphan).
        parent_id = node.get("parent_id")
        for s in subs:
            await update_folder(db, actor_id, s["id"], parent_id=parent_id)
        if assets:
            await db.media_assets.update_many(
                {"folder_id": fid}, {"$set": {"folder_id": parent_id, "updated_at": now_iso()}}
            )
        moved = len(assets)
    await db.media_folders.delete_one({"id": fid})
    await log_action(actor_id, "delete", "media_folders", fid,
                     {"cascade": cascade, "moved_assets": moved})
    return {"deleted": True, "id": fid, "moved_assets": moved,
            "moved_folders": 0 if cascade else len(subs), "cascade": cascade}


async def _descendant_ids(db, fid: str):
    node = await db.media_folders.find_one({"id": fid}, {"_id": 0, "path": 1})
    if not node:
        return [fid]
    prefix = node["path"].rstrip("/") + "/"
    kids = await db.media_folders.find(
        {"path": {"$regex": f"^{re.escape(prefix)}"}}, {"_id": 0, "id": 1}
    ).to_list(2000)
    return [fid] + [k["id"] for k in kids]


# ============================== IMAGE PIPELINE ==============================
async def ensure_default_folders(db, actor_id: str = "system"):
    """Buat folder standar bila belum ada (idempotent)."""
    created = []
    for name in ("Produk", "Banner", "Konten", "Logo & Ikon"):
        exists = await db.media_folders.find_one(
            {"parent_id": None, "name": re.compile(f"^{re.escape(name)}$", re.I)}, {"_id": 1}
        )
        if not exists:
            try:
                f = await create_folder(db, actor_id, name, None)
                created.append(f["name"])
            except MediaError:
                pass
    return created


async def ensure_folder_by_name(db, name: str, actor_id: str = "system"):
    """Kembalikan id folder root ber-nama `name`; buat bila belum ada (idempotent)."""
    clean = _slug_name(name, "Folder")
    doc = await db.media_folders.find_one(
        {"parent_id": None, "name": re.compile(f"^{re.escape(clean)}$", re.I)}, {"_id": 0, "id": 1}
    )
    if doc:
        return doc["id"]
    try:
        created = await create_folder(db, actor_id, clean, None)
        return created["id"]
    except MediaError:
        return None


# ============================== LOKALISASI URL EKSTERNAL ==============================
