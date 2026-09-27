"""services/search.py — pencarian produk toleran typo + singkatan (in-memory, ±1–5 rb produk).

- Normalisasi: huruf kecil, tanpa aksen, "D&G" → "dg", tanda baca dibuang.
- Token dicocokkan ke kosakata indeks: sama persis > awalan > substring > typo (OSA/Damerau ≤1–2).
- Singkatan: inisial otomatis dari nama & brand (mis. "Yves Saint Laurent" → "ysl") + alias bawaan
  + alias admin (Pengaturan › search_aliases, baris "ysl = yves saint laurent"). Dua arah.
- Semua token kueri wajib cocok (AND); bila kosong, longgarkan ke ≥ separuh token.
Indeks di-cache 30 dtk (atau invalidate()).
"""
import re
import time
import unicodedata
from collections import defaultdict

from rapidfuzz.distance import OSA

CACHE_TTL = 30
MAX_RANKED = 300
W_NAME, W_BRAND, W_META, W_NOTE = 1.0, 0.95, 0.7, 0.6
DEFAULT_ALIASES = {
    "ysl": "yves saint laurent", "ck": "calvin klein", "jpg": "jean paul gaultier", "dg": "dolce gabbana",
    "tf": "tom ford", "mfk": "maison francis kurkdjian", "pdm": "parfums de marly", "cd": "christian dior",
    "ga": "giorgio armani", "ch": "carolina herrera", "vs": "victorias secret", "hb": "hugo boss",
    "lv": "louis vuitton", "jm": "jo malone", "ea": "elizabeth arden", "af": "abercrombie fitch",
    "bvlgari": "bulgari", "cp": "collector parfum",
}
STOPWORDS = {"di", "de", "da", "du", "la", "le", "el", "the", "of", "pour", "for", "and", "dan", "by", "eau", "parfum"}
_index = {"at": 0.0, "data": None}


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"(?<=[a-z0-9])[&'’](?=[a-z0-9])", "", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def tokens(s) -> list:
    return norm(s).split()


def _acronyms(words):
    words = [w for w in words if w.isalpha()]
    out = set()
    for size in range(2, 5):
        for i in range(0, len(words) - size + 1):
            out.add("".join(w[0] for w in words[i:i + size]))
    return out


def parse_aliases(text) -> dict:
    out = {}
    for line in str(text or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            k, v = norm(k).replace(" ", ""), norm(v)
            if k and v:
                out[k] = v
    return out


def _entry_tokens(p, aliases):
    """{token: weight} + set akronim untuk satu produk."""
    tw = {}

    def add(ts, w):
        for t in ts:
            if tw.get(t, 0) < w:
                tw[t] = w

    name_t, brand_t = tokens(p.get("name")), tokens(p.get("brand"))
    add(name_t, W_NAME)
    add(["".join(name_t[i:i + 2]) for i in range(len(name_t) - 1)], W_NAME * 0.9)  # "blackopium"
    add(brand_t, W_BRAND)
    add(tokens(p.get("category")) + tokens(p.get("gender")) + tokens(p.get("tier")), W_META)
    add([t for c in (p.get("characters") or []) for t in tokens(c)], W_META)
    notes = p.get("notes") or {}
    add([t for v in list(p.get("tags") or []) + [n for k in ("top", "heart", "base") for n in (notes.get(k) or [])]
         for t in tokens(v)], W_NOTE)
    acr = _acronyms(name_t) | _acronyms(brand_t)
    joined = " " + " ".join(name_t + brand_t) + " "
    for key, phrase in aliases.items():
        if f" {phrase} " in joined:
            acr.add(key)                       # "calvin klein" di produk → cocok dgn "ck"
        if key in tw:
            add(phrase.split(), W_NAME * 0.9)  # "YSL ..." di produk → cocok dgn "yves saint laurent"
    return tw, acr


async def _build(db):
    settings = await db.settings.find_one({"id": "store"}, {"search_aliases": 1}) or {}
    aliases = {**DEFAULT_ALIASES, **parse_aliases(settings.get("search_aliases"))}
    cats = {c["slug"]: c.get("name", "") for c in await db.categories.find({}, {"slug": 1, "name": 1}).to_list(500)}
    chars = {c["slug"]: c.get("name", "") for c in await db.characters.find({}, {"slug": 1, "name": 1}).to_list(500)}
    docs = await db.products.find(
        {"status": "active"},
        {"_id": 0, "id": 1, "name": 1, "brand": 1, "category": 1, "gender": 1, "tier": 1, "characters": 1,
         "tags": 1, "notes": 1, "best_seller": 1}).to_list(20000)
    vocab, acr_map, terms = defaultdict(dict), defaultdict(set), {}
    for i, p in enumerate(docs):
        p = {**p, "category": cats.get(p.get("category"), p.get("category")),
             "characters": [chars.get(c, c) for c in (p.get("characters") or [])]}
        tw, acr = _entry_tokens(p, aliases)
        for t, w in tw.items():
            vocab[t][i] = w
        for a in acr:
            acr_map[a].add(i)
        for label, kind in ([(p.get("brand"), "Brand"), (p.get("category"), "Kategori")]
                            + [(c, "Karakter") for c in p["characters"]]
                            + [(t, "Notes") for t in (p.get("tags") or [])]):
            if label and norm(label):
                terms.setdefault(norm(label), {"label": str(label), "type": kind, "count": 0})["count"] += 1
    return {"docs": docs, "vocab": dict(vocab), "acr": dict(acr_map), "terms": terms, "aliases": aliases}


async def get_index(db):
    if not _index["data"] or time.time() - _index["at"] > CACHE_TTL:
        _index["data"], _index["at"] = await _build(db), time.time()
    return _index["data"]


def invalidate():
    _index["data"] = None


def token_score(qt: str, t: str) -> float:
    if t == qt:
        return 1.0
    n = len(qt)
    if n >= 2 and t.startswith(qt):
        return 0.9 if n >= 3 else 0.6
    if n >= 4 and qt in t:
        return 0.7
    if n >= 3 and not qt.isdigit():  # angka tak di-fuzzy ("1000" ≠ "2000")
        maxd = 1 if n <= 5 else 2
        if abs(len(t) - n) <= maxd:
            d = OSA.distance(qt, t, score_cutoff=maxd)
            if d <= maxd:
                return 0.8 - 0.1 * d
        if n >= 4 and len(t) > n and OSA.distance(qt, t[:n], score_cutoff=1) <= 1:
            return 0.6  # sedang mengetik + typo: "blak op" → "black opium"
    return 0.0


def _match_token(idx, qt):
    """{doc_idx: skor} + token kosakata terbaik (utk 'mungkin maksud Anda')."""
    best, best_tok, best_s = {}, None, 0.0
    for t, postings in idx["vocab"].items():
        s = token_score(qt, t)
        if not s:
            continue
        if s > best_s or (s == best_s and best_tok and len(postings) > len(idx["vocab"][best_tok])):
            best_tok, best_s = t, s
        for i, w in postings.items():
            if s * w > best.get(i, 0):
                best[i] = s * w
    for i in idx["acr"].get(qt, ()) if len(qt) >= 2 else ():
        if best.get(i, 0) < 0.85:
            best[i] = 0.85
    phrase = idx["aliases"].get(qt)
    if phrase:  # "ysl" → cocokkan juga frasa lengkap
        parts = [_match_token(idx, p)[0] for p in phrase.split() if p != qt]
        common = set.intersection(*(set(x) for x in parts)) if parts else set()
        for i in common:
            best[i] = max(best.get(i, 0), 0.9 * min(x[i] for x in parts))
    return best, best_tok, best_s


def rank(idx, q: str):
    """Return (ranked_doc_indices, did_you_mean|None)."""
    qts = tokens(q)[:6]
    core = [t for t in qts if t not in STOPWORDS]
    qts = core or qts  # "aqua di gio" → kata sambung tak wajib cocok
    if not qts:
        return [], None
    per = [_match_token(idx, qt) for qt in qts]
    scores = [p[0] for p in per]
    need = len(qts)
    total = defaultdict(float)
    hits = defaultdict(int)
    for sc in scores:
        for i, s in sc.items():
            total[i] += s
            hits[i] += 1
    chosen = [i for i in total if hits[i] >= need]
    if not chosen and len(qts) > 1:
        chosen = [i for i in total if hits[i] * 2 >= len(qts)]
    nq = norm(q)
    docs = idx["docs"]

    def score(i):
        name = norm(docs[i].get("name"))
        bonus = 0.5 if name == nq else 0.25 if name.startswith(nq) else 0.0
        return total[i] / len(qts) * (hits[i] / len(qts)) + bonus + (0.02 if docs[i].get("best_seller") else 0)
    chosen.sort(key=lambda i: (-score(i), docs[i].get("name", "")))
    fixed = [tok if (tok and s < 0.9 and qt not in idx["acr"] and qt not in idx["aliases"]) else qt
             for qt, (_, tok, s) in zip(qts, per)]
    did_you_mean = " ".join(fixed) if fixed != qts else None
    return chosen[:MAX_RANKED], did_you_mean


async def ranked_ids(db, q: str):
    idx = await get_index(db)
    order, dym = rank(idx, q)
    return [idx["docs"][i]["id"] for i in order], dym


async def suggest_terms(db, q: str, limit=6):
    idx = await get_index(db)
    qts = tokens(q)[:6]
    if not qts:
        return []
    out = []
    for key, term in idx["terms"].items():
        tt = key.split()
        s = [max((token_score(qt, t) for t in tt), default=0) for qt in qts]
        if all(s):
            out.append((sum(s) / len(s), term["count"], term))
    out.sort(key=lambda x: (-x[0], -x[1]))
    return [{"label": t["label"], "type": t["type"], "count": t["count"]} for _, _, t in out[:limit]]
