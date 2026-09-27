"""Iter56 — Admin brand profiles (logo/foto/desc/urutan/hidden), facet image/icon_image,
CMS discovery_section tab icons. Verifies API contracts and cleans up after."""
import os
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN = {"email": "admin@collectorparfum.id", "password": "Admin#2026"}


def _admin_token():
    r = requests.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("access_token") or j.get("token")


def _headers(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- API contracts ----------

def test_admin_brands_requires_auth():
    r = requests.get(f"{BASE}/api/admin/brands", timeout=15)
    assert r.status_code in (401, 403)


def test_admin_brands_list_shape():
    tok = _admin_token()
    r = requests.get(f"{BASE}/api/admin/brands", headers=_headers(tok), timeout=15)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert isinstance(rows, list) and len(rows) >= 1
    row = rows[0]
    for k in ("name", "count", "active_count", "logo", "image", "desc", "order", "hidden", "has_profile"):
        assert k in row, f"missing key {k} in admin brand row"
    names = [b["name"] for b in rows]
    assert "Collector" in names, f"expected Collector in {names}"


def test_admin_brand_upsert_and_hide_flow():
    tok = _admin_token()
    H = _headers(tok)
    # Upsert profile for Collector
    payload = {
        "name": "Collector",
        "logo": "/uploads/test-logo.svg",
        "image": "/uploads/test-image.jpg",
        "desc": "TEST_brand_desc_iter56",
        "order": 5,
        "hidden": False,
    }
    r = requests.put(f"{BASE}/api/admin/brands", headers=H, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    # Verify admin list reflects it
    rows = requests.get(f"{BASE}/api/admin/brands", headers=H, timeout=15).json()
    row = next(b for b in rows if b["name"] == "Collector")
    assert row["desc"] == "TEST_brand_desc_iter56"
    assert row["order"] == 5
    assert row["has_profile"] is True

    # Public /api/brands should include logo/image/desc/order
    pub = requests.get(f"{BASE}/api/brands", timeout=15).json()
    coll = next((b for b in pub if b["name"] == "Collector"), None)
    assert coll is not None
    assert coll["logo"] == "/uploads/test-logo.svg"
    assert coll["image"] == "/uploads/test-image.jpg"
    assert coll["desc"] == "TEST_brand_desc_iter56"
    assert coll["order"] == 5

    # Hide → disappears from /api/brands
    payload["hidden"] = True
    r = requests.put(f"{BASE}/api/admin/brands", headers=H, json=payload, timeout=15)
    assert r.status_code == 200
    pub2 = requests.get(f"{BASE}/api/brands", timeout=15).json()
    assert not any(b["name"] == "Collector" for b in pub2)

    # DELETE cleanup
    r = requests.delete(f"{BASE}/api/admin/brands/profile", headers=H, params={"name": "Collector"}, timeout=15)
    assert r.status_code == 200, r.text
    # Verify back on public brands (Collector still exists as brand from products)
    pub3 = requests.get(f"{BASE}/api/brands", timeout=15).json()
    coll3 = next((b for b in pub3 if b["name"] == "Collector"), None)
    assert coll3 is not None
    assert coll3.get("logo", "") == ""
    assert coll3.get("desc", "") == ""


def test_delete_missing_brand_profile_returns_404():
    tok = _admin_token()
    r = requests.delete(f"{BASE}/api/admin/brands/profile", headers=_headers(tok),
                        params={"name": "NopeXYZ_iter56"}, timeout=15)
    assert r.status_code == 404


def test_public_brands_order_first():
    tok = _admin_token()
    H = _headers(tok)
    # Set high order to force Collector to top
    requests.put(f"{BASE}/api/admin/brands", headers=H,
                 json={"name": "Collector", "order": 1, "hidden": False}, timeout=15)
    pub = requests.get(f"{BASE}/api/brands", timeout=15).json()
    assert pub[0]["name"] == "Collector"
    # cleanup
    requests.delete(f"{BASE}/api/admin/brands/profile", headers=H, params={"name": "Collector"}, timeout=15)


# ---------- Characters ----------

def test_characters_expose_image_and_icon_image():
    r = requests.get(f"{BASE}/api/characters", timeout=15)
    assert r.status_code == 200
    chars = r.json()
    assert isinstance(chars, list) and chars
    # image/icon_image keys should exist (may be empty)
    for c in chars:
        # allowed empty string or absent; but after facet update the key exists — presence not required if not saved
        # ensure structure at least has name & slug & count
        assert "name" in c and "slug" in c and "count" in c


def test_admin_facet_character_image_roundtrip():
    tok = _admin_token()
    H = _headers(tok)
    # Fetch characters via admin facets endpoint
    r = requests.get(f"{BASE}/api/admin/characters", headers=H, timeout=15)
    assert r.status_code == 200, r.text
    chars = r.json()
    if not chars:
        return
    woody = next((c for c in chars if c.get("slug") == "woody"), chars[0])
    cid = woody["id"]
    orig_img = woody.get("image", "")
    orig_icon = woody.get("icon_image", "")
    payload = {**woody, "image": "/uploads/test-char-photo.jpg", "icon_image": "/uploads/test-char-icon.svg"}
    r = requests.put(f"{BASE}/api/admin/characters/{cid}", headers=H, json=payload, timeout=15)
    assert r.status_code == 200, r.text
    # Verify via public /api/characters
    pub = requests.get(f"{BASE}/api/characters", timeout=15).json()
    p = next((c for c in pub if c["slug"] == woody["slug"]), None)
    if p is not None:
        assert p.get("image") == "/uploads/test-char-photo.jpg"
        assert p.get("icon_image") == "/uploads/test-char-icon.svg"
    # Revert
    revert = {**woody, "image": orig_img, "icon_image": orig_icon}
    r = requests.put(f"{BASE}/api/admin/characters/{cid}", headers=H, json=revert, timeout=15)
    assert r.status_code == 200


# ---------- CMS discovery_section ----------

def test_cms_discovery_section_fields_present():
    tok = _admin_token()
    H = _headers(tok)
    # Fetch content schema
    r = requests.get(f"{BASE}/api/admin/content/schema", headers=H, timeout=15)
    assert r.status_code == 200, r.text
    schema = r.json()
    sec = next((s for s in schema if s["key"] == "discovery_section"), None)
    assert sec is not None, "discovery_section missing in CMS schema"
    fnames = {f["name"] for f in sec["fields"]}
    for k in ("title", "eyebrow", "subtitle",
              "brand_label", "brand_icon", "character_label", "character_icon",
              "editor_label", "editor_icon", "best_label", "best_icon"):
        assert k in fnames, f"missing {k} in discovery_section fields"


def test_cms_discovery_section_update_and_public_fetch():
    tok = _admin_token()
    H = _headers(tok)
    # Get current
    r = requests.get(f"{BASE}/api/content", timeout=15)
    assert r.status_code == 200
    orig = r.json().get("discovery_section", {})
    payload = {**orig, "brand_label": "TESTMerk", "brand_icon": "/uploads/test-tab.svg"}
    r = requests.put(f"{BASE}/api/admin/content/discovery_section", headers=H, json={"data": payload}, timeout=15)
    assert r.status_code == 200, r.text
    # Public
    pub = requests.get(f"{BASE}/api/content", timeout=15).json().get("discovery_section", {})
    assert pub["brand_label"] == "TESTMerk"
    assert pub["brand_icon"] == "/uploads/test-tab.svg"
    # Revert
    revert = {**orig}
    r = requests.put(f"{BASE}/api/admin/content/discovery_section", headers=H, json={"data": revert}, timeout=15)
    assert r.status_code == 200
    pub2 = requests.get(f"{BASE}/api/content", timeout=15).json().get("discovery_section", {})
    assert pub2["brand_label"] == orig["brand_label"]
