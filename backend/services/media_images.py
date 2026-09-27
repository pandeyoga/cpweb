"""services/media_images.py — Pemrosesan gambar (Pillow) + serialisasi aset publik + tulis berkas. (dipecah dari services/media.py; API publik via services.media)."""
import io
from datetime import datetime, timezone

from PIL import Image, ImageOps, ImageSequence  # noqa: F401

from services.media_core import (
    DERIVED_DIR,
    EXT_MAP,
    MAX_DIM,
    MEDIUM_DIM,
    ORIGINALS_DIR,
    PASSTHROUGH_MIME,
    SAVE_AS,
    THUMB_DIM,
    MediaError,
    _mirror_put,
    _rel,
)


def _flatten(im):
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert("RGB")


def _encode(im, fmt: str) -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG":
        _flatten(im).save(buf, "JPEG", quality=88, optimize=True, progressive=True)
    elif fmt == "PNG":
        (im if im.mode in ("RGBA", "RGB", "P", "L") else im.convert("RGBA")).save(
            buf, "PNG", optimize=True
        )
    elif fmt == "WEBP":
        (im if im.mode in ("RGBA", "RGB") else im.convert("RGBA")).save(
            buf, "WEBP", quality=86, method=5
        )
    elif fmt == "AVIF":
        try:
            (im if im.mode in ("RGBA", "RGB") else im.convert("RGB")).save(
                buf, "AVIF", quality=75
            )
        except Exception:
            buf = io.BytesIO()
            _flatten(im).save(buf, "JPEG", quality=88, optimize=True)
    else:  # pragma: no cover
        _flatten(im).save(buf, "JPEG", quality=88, optimize=True)
    return buf.getvalue()


def _thumb_bytes(im, dim: int) -> bytes:
    c = im.copy()
    c.thumbnail((dim, dim), Image.LANCZOS)
    buf = io.BytesIO()
    if c.mode not in ("RGB", "RGBA"):
        c = c.convert("RGBA" if "A" in c.getbands() else "RGB")
    c.save(buf, "WEBP", quality=82, method=5)
    return buf.getvalue()


def process_image(data: bytes, mime: str):
    """Optimasi + turunan. Kembalikan dict siap ditulis ke disk.

    keys: data, ext, mime, width, height, thumb, medium, animated
    """
    if mime in PASSTHROUGH_MIME:
        return {"data": data, "ext": "svg", "mime": mime, "width": None,
                "height": None, "thumb": None, "medium": None, "animated": False}
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        raise MediaError("Berkas bukan gambar yang valid atau format tidak didukung")

    animated = bool(getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1)
    if animated:
        # GIF/WebP animasi: simpan apa adanya agar animasi tidak hilang.
        ext = EXT_MAP.get(mime, "gif")
        try:
            first = ImageSequence.Iterator(im)[0].convert("RGBA")
            thumb = _thumb_bytes(first, THUMB_DIM)
        except Exception:
            thumb = None
        return {"data": data, "ext": ext, "mime": mime, "width": im.size[0],
                "height": im.size[1], "thumb": thumb, "medium": None, "animated": True}

    try:
        im = ImageOps.exif_transpose(im) or im
    except Exception:  # best-effort: kegagalan sekunder media tak boleh memblokir alur utama
        pass
    fmt, ext, out_mime = SAVE_AS.get(mime, ("JPEG", "jpg", "image/jpeg"))
    work = im
    if max(work.size) > MAX_DIM:
        work = work.copy()
        work.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
    out = _encode(work, fmt)
    # Bila optimasi malah membengkak (dan format sama), pakai biner asli.
    if mime == out_mime and len(out) > len(data) and max(im.size) <= MAX_DIM:
        out = data
    return {
        "data": out, "ext": ext, "mime": out_mime,
        "width": work.size[0], "height": work.size[1],
        "thumb": _thumb_bytes(work, THUMB_DIM),
        "medium": _thumb_bytes(work, MEDIUM_DIM) if max(work.size) > MEDIUM_DIM else None,
        "animated": False,
    }


# ============================== ASSETS ==============================
def public_asset(d: dict) -> dict:
    """Bentuk respons publik aset (kontrak FE)."""
    if not d:
        return None
    return {
        "id": d.get("id"),
        "folder_id": d.get("folder_id"),
        "filename": d.get("filename") or d.get("original_name") or "media",
        "url": d.get("url"),
        "thumb_url": d.get("thumb_url") or d.get("url"),
        "medium_url": d.get("medium_url") or d.get("url"),
        "kind": d.get("kind") or "image",
        "mime": d.get("mime"),
        "size": int(d.get("size") or 0),
        "width": d.get("width"),
        "height": d.get("height"),
        "alt": d.get("alt"),
        "title": d.get("title"),
        "tags": d.get("tags") or [],
        "source": d.get("source") or ("upload" if d.get("stored_path") else "url"),
        "external": bool(d.get("source") == "external"),
        "stored_path": d.get("stored_path"),
        "uploaded_by": d.get("uploaded_by") or d.get("owner_admin_id"),
        "uploaded_at": d.get("uploaded_at") or d.get("created_at"),
        "updated_at": d.get("updated_at") or d.get("uploaded_at") or d.get("created_at"),
    }


async def _write_files(db, base_uuid: str, proc: dict):
    """Tulis asli + turunan ke disk & mirror. Kembalikan (stored_rel, thumb_rel, medium_rel)."""
    now = datetime.now(timezone.utc)
    sub = ORIGINALS_DIR / f"{now.year:04d}" / f"{now.month:02d}"
    sub.mkdir(parents=True, exist_ok=True)
    orig_path = sub / f"{base_uuid}.{proc['ext']}"
    with open(orig_path, "wb") as f:
        f.write(proc["data"])
    stored_rel = _rel(orig_path)
    await _mirror_put(db, stored_rel, proc["data"], proc["mime"])

    thumb_rel = medium_rel = None
    if proc.get("thumb"):
        DERIVED_DIR.mkdir(parents=True, exist_ok=True)
        tp = DERIVED_DIR / f"{base_uuid}_{THUMB_DIM}.webp"
        with open(tp, "wb") as f:
            f.write(proc["thumb"])
        thumb_rel = _rel(tp)
        await _mirror_put(db, thumb_rel, proc["thumb"], "image/webp")
    if proc.get("medium"):
        mp = DERIVED_DIR / f"{base_uuid}_{MEDIUM_DIM}.webp"
        with open(mp, "wb") as f:
            f.write(proc["medium"])
        medium_rel = _rel(mp)
        await _mirror_put(db, medium_rel, proc["medium"], "image/webp")
    return stored_rel, thumb_rel, medium_rel
