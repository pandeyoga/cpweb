"""Iter60 tests: day_night migration + admin roundtrip + CSV export + discovery_section (brand_limit/brand_sort)."""
import os
import io
import csv
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://cpweb-preview-test.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@collectorparfum.id"
ADMIN_PASS = "Admin#2026"


def _items(resp_json):
    """Public list endpoints return a JSON array directly."""
    if isinstance(resp_json, list):
        return resp_json
    return resp_json.get("items", [])


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "X-Admin-Token": admin_token, "Content-Type": "application/json"}


# --- Migration: no legacy date_night field, day_night set (via public list)
def test_products_have_day_night_no_legacy():
    r = requests.get(f"{BASE}/api/products?limit=100", timeout=15)
    assert r.status_code == 200
    items = _items(r.json())
    assert len(items) > 0
    for p in items:
        assert "date_night" not in p, f"legacy date_night present in product {p.get('id')}"
        assert "day_night" in p, f"day_night missing in product {p.get('id')}"
        assert p["day_night"] in ("", "day", "night", "both")


def test_filter_day_only():
    r = requests.get(f"{BASE}/api/products?day_night=day&limit=100", timeout=15)
    assert r.status_code == 200
    for p in _items(r.json()):
        assert p["day_night"] in ("day", "both"), p


def test_filter_night_only():
    r = requests.get(f"{BASE}/api/products?day_night=night&limit=100", timeout=15)
    assert r.status_code == 200
    for p in _items(r.json()):
        assert p["day_night"] in ("night", "both"), p


def test_filter_day_and_night():
    r = requests.get(f"{BASE}/api/products?day_night=day,night&limit=100", timeout=15)
    assert r.status_code == 200
    for p in _items(r.json()):
        assert p["day_night"] in ("day", "night", "both"), p


def test_legacy_date_night_query_maps_to_both():
    r = requests.get(f"{BASE}/api/products?date_night=1&limit=100", timeout=15)
    assert r.status_code == 200
    for p in _items(r.json()):
        assert p["day_night"] == "both", p


def test_legacy_occasion_date_night_maps_to_both():
    r = requests.get(f"{BASE}/api/products?occasion=date-night&limit=100", timeout=15)
    assert r.status_code == 200
    for p in _items(r.json()):
        assert p["day_night"] == "both", p


def test_garbage_day_night_ignored_no_5xx():
    r = requests.get(f"{BASE}/api/products?day_night=foobar,%20,;,42&limit=10", timeout=15)
    assert r.status_code == 200


def test_x_total_count_header_present():
    r = requests.get(f"{BASE}/api/products?limit=5", timeout=15)
    assert r.status_code == 200
    assert "X-Total-Count" in r.headers
    assert int(r.headers["X-Total-Count"]) >= len(_items(r.json()))


# --- Admin PUT day_night roundtrip
def _get_first_admin_product(admin_headers):
    r = requests.get(f"{BASE}/api/admin/products?limit=1", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    items = _items(r.json())
    assert items, "no admin products found"
    pid = items[0]["id"]
    full = requests.get(f"{BASE}/api/admin/products/{pid}", headers=admin_headers, timeout=15).json()
    return pid, full


def _base_payload(full):
    # Minimal fields the PUT validator requires + preserve slug + variants
    return {
        "name": full.get("name", "Test"),
        "category": full.get("category", "floral"),
        "brand": full.get("brand", ""),
        "slug": full.get("slug"),
        "price": full.get("price", 0),
        "gender": full.get("gender", ""),
        "tier": full.get("tier", ""),
        "variants": full.get("variants") or [],
        "options": full.get("options") or [],
        "images": full.get("images") or [],
    }


def test_admin_put_day_night_valid_values(admin_headers):
    pid, full = _get_first_admin_product(admin_headers)
    original = full.get("day_night", "")
    base = _base_payload(full)
    try:
        for val in ("day", "night", "both", ""):
            r = requests.put(f"{BASE}/api/admin/products/{pid}", headers=admin_headers,
                             json={**base, "day_night": val}, timeout=15)
            assert r.status_code == 200, f"PUT {val} failed: {r.status_code} {r.text}"
            r2 = requests.get(f"{BASE}/api/admin/products/{pid}", headers=admin_headers, timeout=15)
            assert r2.status_code == 200
            assert r2.json().get("day_night") == val, f"expected {val!r}, got {r2.json().get('day_night')!r}"
    finally:
        requests.put(f"{BASE}/api/admin/products/{pid}", headers=admin_headers,
                     json={**base, "day_night": original}, timeout=15)


def test_admin_put_day_night_invalid_returns_422(admin_headers):
    pid, full = _get_first_admin_product(admin_headers)
    base = _base_payload(full)
    r = requests.put(f"{BASE}/api/admin/products/{pid}", headers=admin_headers,
                     json={**base, "day_night": "midnight"}, timeout=15)
    assert r.status_code == 422, f"expected 422 for invalid day_night, got {r.status_code}: {r.text[:300]}"


# --- CSV export
def test_csv_export_has_day_night_no_legacy(admin_headers):
    r = requests.get(f"{BASE}/api/admin/products/io/export?format=csv", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    text = r.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    assert rows, "empty CSV"
    header = rows[0]
    assert "day_night" in header, f"day_night column missing. header={header}"
    assert "date_night" not in header, f"legacy date_night column still present: {header}"
    idx = header.index("day_night")
    for row in rows[1:]:
        if len(row) > idx:
            val = row[idx]
            assert val in ("", "Day", "Night", "Day/Night"), f"unexpected label: {val!r}"


# --- Discovery CMS: brand_limit + brand_sort
def test_discovery_section_defaults():
    r = requests.get(f"{BASE}/api/content", timeout=15)
    assert r.status_code == 200
    d = r.json().get("discovery_section", {})
    assert str(d.get("brand_limit")) == "12"
    assert d.get("brand_sort") == "count"


def test_discovery_section_put_and_revert(admin_headers):
    # Get current
    orig = requests.get(f"{BASE}/api/content", timeout=15).json().get("discovery_section", {})
    payload = {**orig, "brand_limit": "1", "brand_sort": "name"}
    put = requests.put(f"{BASE}/api/admin/content/discovery_section", headers=admin_headers,
                       json={"data": payload}, timeout=15)
    assert put.status_code == 200, put.text
    d = requests.get(f"{BASE}/api/content", timeout=15).json().get("discovery_section", {})
    assert str(d.get("brand_limit")) == "1"
    assert d.get("brand_sort") == "name"
    # Revert
    rev = requests.post(f"{BASE}/api/admin/content/discovery_section/revert",
                        headers=admin_headers, json={"to_default": True}, timeout=15)
    assert rev.status_code == 200, rev.text
    d2 = requests.get(f"{BASE}/api/content", timeout=15).json().get("discovery_section", {})
    assert str(d2.get("brand_limit")) == "12"
    assert d2.get("brand_sort") == "count"


def test_brands_endpoint_returns_list_with_counts():
    r = requests.get(f"{BASE}/api/brands", timeout=15)
    assert r.status_code == 200
    items = _items(r.json())
    assert isinstance(items, list) and len(items) > 0
    for b in items:
        assert "name" in b and "count" in b
        assert isinstance(b["count"], int) and b["count"] >= 1


def test_reviews_regression_ok():
    r = requests.get(f"{BASE}/api/reviews", timeout=15)
    assert r.status_code == 200, r.text
