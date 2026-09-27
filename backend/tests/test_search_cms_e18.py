"""E18: pencarian toleran typo/singkatan + saran instan; rollback CMS persis ke snapshot."""
import asyncio
import os
from collections import defaultdict

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from services import search as S

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def admin_h():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@collectorparfum.id", "password": "Admin#2026"}, timeout=30)
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _idx(docs, aliases=None):
    aliases = aliases or S.DEFAULT_ALIASES
    vocab, acr = defaultdict(dict), defaultdict(set)
    for i, p in enumerate(docs):
        tw, a = S._entry_tokens(p, aliases)
        for t, w in tw.items():
            vocab[t][i] = w
        for x in a:
            acr[x].add(i)
    return {"docs": docs, "vocab": dict(vocab), "acr": dict(acr), "terms": {}, "aliases": aliases}


DOCS = [
    {"id": "a", "name": "Yves Saint Laurent Black Opium", "brand": "Yves Saint Laurent"},
    {"id": "b", "name": "Calvin Klein ONE", "brand": "Calvin Klein"},
    {"id": "c", "name": "Dolce & Gabbana Light Blue", "brand": "Dolce & Gabbana"},
    {"id": "d", "name": "Giorgio Armani Aqua DE GIO", "brand": "Giorgio Armani"},
    {"id": "e", "name": "1000 Bunga", "brand": "Collector Parfum"},
    {"id": "f", "name": "2000 Bunga", "brand": "Collector Parfum"},
    {"id": "g", "name": "Casablanca Homme", "brand": "Casablanca"},
]


@pytest.mark.parametrize("q,first", [
    ("ysl", "a"), ("blak opum", "a"), ("black opium", "a"), ("ck one", "b"), ("calvn", "b"),
    ("d&g", "c"), ("dg light", "c"), ("aqua di gio", "d"), ("kasablanka", "g"), ("1000 bunga", "e"),
])
def test_rank_typo_and_acronyms(q, first):
    idx = _idx(DOCS)
    order, _ = S.rank(idx, q)
    assert order and DOCS[order[0]]["id"] == first, (q, [DOCS[i]["id"] for i in order])


def test_numbers_not_fuzzy_and_did_you_mean():
    idx = _idx(DOCS)
    order, _ = S.rank(idx, "1000")
    assert [DOCS[i]["id"] for i in order] == ["e"]
    _, dym = S.rank(idx, "casablnca")
    assert dym == "casablanca"


def test_admin_alias_both_directions():
    idx = _idx(DOCS, {**S.DEFAULT_ALIASES, **S.parse_aliases("chm = casablanca homme\nbadaa = light blue")})
    assert DOCS[S.rank(idx, "chm")[0][0]]["id"] == "g"
    assert DOCS[S.rank(idx, "badaa")[0][0]]["id"] == "c"


def test_api_typo_search_and_header():
    r = requests.get(f"{BASE}/products", params={"q": "nior oud"}, timeout=30)
    assert r.status_code == 200 and r.json()[0]["slug"] == "noir-oud-intense"
    assert r.headers.get("X-Did-You-Mean") == "noir oud"
    r2 = requests.get(f"{BASE}/products", params={"q": "velvt vanila", "limit": 3}, timeout=30)
    assert r2.json()[0]["name"] == "Velvet Vanilla Noir"
    r3 = requests.get(f"{BASE}/products", params={"q": "zzqxw"}, timeout=30)
    assert r3.json() == [] and r3.headers["X-Total-Count"] == "0"


def test_api_search_respects_other_filters_and_sort():
    r = requests.get(f"{BASE}/products", params={"q": "noir", "sort": "high"}, timeout=30)
    prices = [p["price"] for p in r.json()]
    assert len(prices) >= 2 and prices == sorted(prices, reverse=True)
    r2 = requests.get(f"{BASE}/products", params={"q": "noir", "date_night": "1"}, timeout=30)
    assert all(p["date_night"] for p in r2.json())


def test_suggest_endpoint():
    d = requests.get(f"{BASE}/search/suggest", params={"q": "vanil"}, timeout=30).json()
    assert d["total"] >= 1 and d["products"][0]["name"] == "Velvet Vanilla Noir"
    assert any(t["label"].lower() == "vanilla" for t in d["terms"])
    empty = requests.get(f"{BASE}/search/suggest", params={"q": ""}, timeout=30).json()
    assert empty["products"] == [] and empty["total"] == 0


def test_settings_alias_applies_to_search(admin_h):
    before = requests.get(f"{BASE}/admin/settings", headers=admin_h, timeout=30).json().get("search_aliases") or ""
    try:
        assert requests.put(f"{BASE}/admin/settings", json={"search_aliases": "nox = noir oud intense"},
                            headers=admin_h, timeout=30).status_code == 200
        r = requests.get(f"{BASE}/products", params={"q": "nox"}, timeout=30)
        assert [p["slug"] for p in r.json()][:1] == ["noir-oud-intense"]
    finally:
        requests.put(f"{BASE}/admin/settings", json={"search_aliases": before}, headers=admin_h, timeout=30)


def test_cms_revert_is_exact_snapshot(admin_h):
    schema = requests.get(f"{BASE}/admin/content/schema", headers=admin_h, timeout=30).json()
    sec = next(s for s in schema if sum(f["type"] == "text" for f in s["fields"]) >= 2)
    key = sec["key"]
    f1, f2 = [f["name"] for f in sec["fields"] if f["type"] == "text"][:2]
    original = _run(_db().content.find_one({"id": key}, {"_id": 0}))
    try:
        _run(_db().content.update_one({"id": key}, {"$set": {"data": {f1: "SNAP-A"}}}, upsert=True))
        requests.put(f"{BASE}/admin/content/{key}", json={"data": {f2: "BARU-B"}}, headers=admin_h, timeout=30)
        revs = requests.get(f"{BASE}/admin/content/{key}/revisions", headers=admin_h, timeout=30).json()["revisions"]
        target = revs[0]
        assert target["data"] == {f1: "SNAP-A"} and target["created_by_name"]
        assert any(lbl for lbl in target["changed_fields"])
        snap = requests.get(f"{BASE}/admin/content/{key}/revisions/{target['id']}", headers=admin_h, timeout=30).json()
        assert snap["data"][f1] == "SNAP-A" and snap["data"][f2] == sec["default"].get(f2)
        r = requests.post(f"{BASE}/admin/content/{key}/revert", json={"revision_id": target["id"]}, headers=admin_h, timeout=30)
        assert r.status_code == 200
        stored = _run(_db().content.find_one({"id": key}))["data"]
        assert stored == {f1: "SNAP-A"}, stored  # override f2 dihapus
        pub = requests.get(f"{BASE}/content", timeout=30).json()[key]
        assert pub[f2] == sec["default"].get(f2)
        # pemulihan tercatat sebagai revisi baru (bisa dibatalkan)
        revs2 = requests.get(f"{BASE}/admin/content/{key}/revisions", headers=admin_h, timeout=30).json()["revisions"]
        assert revs2[0]["note"] == f"revert:{target['id']}" and revs2[0]["data"][f2] == "BARU-B"
    finally:
        if original:
            _run(_db().content.replace_one({"id": key}, original))
