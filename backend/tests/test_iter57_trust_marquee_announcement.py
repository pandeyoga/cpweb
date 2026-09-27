"""Iteration 57 — Trust Strip, Marquee (kata berjalan), Announcement Bar CMS.

Validates admin CMS can edit these Global/Beranda sections and public /api/content
mirrors changes; revert restores originals.
"""

import os
import copy
import pytest
import requests

def _read_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("REACT_APP_BACKEND_URL", "")


BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _read_env()).rstrip("/")
API = f"{BASE}/api"
ADMIN_EMAIL = "admin@collectorparfum.id"
ADMIN_PASSWORD = "Admin#2026"


@pytest.fixture(scope="module")
def admin_headers():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def schema(admin_headers):
    r = requests.get(f"{API}/admin/content/schema", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    return {s["key"]: s for s in r.json()}


def _fields(schema_map, key):
    return {f["name"]: f for f in schema_map[key]["fields"]}


# ---------------- SCHEMA COVERAGE ----------------

def test_schema_contains_trust_marquee_announcement(schema):
    assert "trust" in schema
    assert "marquee_words" in schema
    assert "announcement" in schema


def test_trust_schema_fields(schema):
    t = schema["trust"]
    # repeater "items" with sub-fields
    items_field = next(f for f in t["fields"] if f["name"] == "items")
    assert items_field["type"] == "repeater"
    sub = {f["name"]: f for f in items_field["item"]}
    for k in ("title", "desc", "icon", "icon_image", "to"):
        assert k in sub, f"missing sub-field {k}"
    assert sub["icon"]["type"] == "select"
    icon_values = [o["value"] for o in sub["icon"]["options"]]
    for expected in ("truck", "shield-check", "rotate-ccw", "store", "map-pin",
                     "award", "badge-check", "gift", "clock", "package",
                     "crown", "sparkles", "heart", "star", "droplets",
                     "leaf", "gem", "sun-moon", "flame"):
        assert expected in icon_values, f"icon option missing: {expected}"
    assert sub["icon_image"]["type"] == "image"


def test_marquee_words_schema_fields(schema):
    fmap = _fields(schema, "marquee_words")
    assert fmap["items"]["type"] == "list"
    assert fmap["speed"]["type"] == "select"
    speeds = [o["value"] for o in fmap["speed"]["options"]]
    for s in ("slow", "default", "fast"):
        assert s in speeds
    assert fmap["style"]["type"] == "select"
    styles = [o["value"] for o in fmap["style"]["options"]]
    for s in ("light", "dark", "brass"):
        assert s in styles
    assert fmap["separator"]["type"] == "text"
    assert fmap["separator_image"]["type"] == "image"


def test_announcement_schema_fields(schema):
    fmap = _fields(schema, "announcement")
    assert fmap["items"]["type"] == "list"
    assert fmap["speed"]["type"] == "select"
    assert fmap["separator"]["type"] == "text"


# ---------------- DEFAULTS / CURRENT VALUE ----------------

def test_public_content_returns_defaults():
    r = requests.get(f"{API}/content", timeout=15)
    assert r.status_code == 200
    data = r.json()
    trust = data["trust"]["items"]
    titles = [i["title"] for i in trust]
    assert "Sejak 1970" in titles
    assert "Biang Impor Pilihan" in titles
    assert "3 Cabang di Bandung" in titles
    # Icons defaults
    by_title = {i["title"]: i for i in trust}
    assert by_title["Sejak 1970"]["icon"] == "award"
    assert by_title["Sejak 1970"]["to"] == "/tentang"
    assert by_title["Biang Impor Pilihan"]["icon"] == "shield-check"
    assert by_title["3 Cabang di Bandung"]["icon"] == "map-pin"
    assert by_title["3 Cabang di Bandung"]["to"] == "/lokasi"

    mq = data["marquee_words"]
    assert isinstance(mq["items"], list) and len(mq["items"]) >= 1
    assert mq["speed"] in ("slow", "default", "fast")
    assert mq["style"] in ("light", "dark", "brass")

    ann = data["announcement"]
    assert isinstance(ann["items"], list) and len(ann["items"]) >= 1


# ---------------- EDIT + PERSIST + REVERT ----------------

def _snapshot(admin_headers, keys):
    r = requests.get(f"{API}/admin/content", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    data = r.json()
    return {k: copy.deepcopy(data.get(k)) for k in keys}


def _put(admin_headers, key, data):
    r = requests.put(f"{API}/admin/content/{key}",
                     headers=admin_headers, json={"data": data}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _revert(admin_headers, key):
    r = requests.post(f"{API}/admin/content/{key}/revert",
                      headers=admin_headers, json={"to_default": True}, timeout=15)
    assert r.status_code == 200, r.text


def test_edit_trust_marquee_announcement_and_revert(admin_headers):
    original = _snapshot(admin_headers, ["trust", "marquee_words", "announcement"])
    try:
        # Trust: 4 items to force grid-4
        trust_payload = {"items": [
            {"title": "TEST_A", "desc": "desc A", "icon": "truck", "icon_image": "", "to": "/shop"},
            {"title": "TEST_B", "desc": "desc B", "icon": "crown", "icon_image": "", "to": ""},
            {"title": "TEST_C", "desc": "desc C", "icon": "sparkles", "icon_image": "/uploads/svg-test.svg", "to": "/tentang"},
            {"title": "TEST_D", "desc": "desc D", "icon": "flame", "icon_image": "", "to": "/lokasi"},
        ]}
        _put(admin_headers, "trust", trust_payload)

        marquee_payload = {
            "items": ["TESTMARQ1", "TESTMARQ2", "TESTMARQ3"],
            "speed": "fast", "style": "dark",
            "separator": "✦", "separator_image": "/uploads/sep-test.svg",
        }
        _put(admin_headers, "marquee_words", marquee_payload)

        announcement_payload = {
            "items": ["TESTANN1", "TESTANN2"],
            "speed": "slow", "separator": "★",
        }
        _put(admin_headers, "announcement", announcement_payload)

        # Public reflects changes
        pub = requests.get(f"{API}/content", timeout=15).json()
        titles = [i["title"] for i in pub["trust"]["items"]]
        assert titles == ["TEST_A", "TEST_B", "TEST_C", "TEST_D"]
        assert pub["trust"]["items"][0]["icon"] == "truck"
        assert pub["trust"]["items"][2]["icon_image"] == "/uploads/svg-test.svg"
        assert pub["trust"]["items"][3]["to"] == "/lokasi"

        assert pub["marquee_words"]["items"] == ["TESTMARQ1", "TESTMARQ2", "TESTMARQ3"]
        assert pub["marquee_words"]["speed"] == "fast"
        assert pub["marquee_words"]["style"] == "dark"
        assert pub["marquee_words"]["separator"] == "✦"
        assert pub["marquee_words"]["separator_image"] == "/uploads/sep-test.svg"

        assert pub["announcement"]["items"] == ["TESTANN1", "TESTANN2"]
        assert pub["announcement"]["speed"] == "slow"
        assert pub["announcement"]["separator"] == "★"
    finally:
        # Revert to defaults exactly as registry
        for k in ("trust", "marquee_words", "announcement"):
            _revert(admin_headers, k)
        # Verify revert (defaults restored)
        pub = requests.get(f"{API}/content", timeout=15).json()
        assert any(i["title"] == "Sejak 1970" for i in pub["trust"]["items"])
        assert pub["marquee_words"]["items"][0] == original["marquee_words"]["items"][0] \
            if original.get("marquee_words") else True


def test_non_admin_cannot_edit():
    r = requests.put(f"{API}/admin/content/trust", json={"data": {"items": []}}, timeout=15)
    assert r.status_code in (401, 403)
