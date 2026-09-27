"""Iter55: Test discovery + shop filter API changes.
- GET /api/brands returns [{name,count,images,sample}]
- GET /api/characters returns count field
- GET /api/products?brand=<name> filter + X-Total-Count
- GET /api/products?sort=rating ordering rating_avg desc
"""
import os
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers["Content-Type"] = "application/json"
    return s


def test_brands_shape(client):
    r = client.get(f"{BASE}/api/brands", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) >= 1
    b = data[0]
    for k in ("name", "count", "images", "sample"):
        assert k in b, f"missing {k}"
    assert isinstance(b["images"], list) and isinstance(b["sample"], list)
    assert isinstance(b["count"], int) and b["count"] >= 1
    # Preview says only 'Collector'
    names = [x["name"] for x in data]
    assert "Collector" in names


def test_characters_have_count(client):
    r = client.get(f"{BASE}/api/characters", timeout=15)
    assert r.status_code == 200
    chars = r.json()
    assert isinstance(chars, list) and len(chars) >= 1
    assert all("count" in c for c in chars)
    # At least one char should have count > 0 given 12 products seed
    assert any((c.get("count") or 0) > 0 for c in chars)


def test_products_brand_filter_collector(client):
    r = client.get(f"{BASE}/api/products", params={"brand": "Collector"}, timeout=15)
    assert r.status_code == 200
    total = r.headers.get("X-Total-Count")
    assert total is not None
    assert int(total) == 12
    for p in r.json():
        assert p.get("brand") == "Collector"


def test_products_brand_filter_nope(client):
    r = client.get(f"{BASE}/api/products", params={"brand": "NopeBrandXYZ"}, timeout=15)
    assert r.status_code == 200
    assert int(r.headers.get("X-Total-Count", "-1")) == 0
    assert r.json() == []


def test_products_sort_rating_desc(client):
    r = client.get(f"{BASE}/api/products", params={"sort": "rating", "limit": 12}, timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 2
    ratings = [float(p.get("rating_avg") or 0) for p in items]
    assert ratings == sorted(ratings, reverse=True), f"Not desc: {ratings}"


def test_products_character_filter(client):
    # pick a character with count > 0
    chars = client.get(f"{BASE}/api/characters", timeout=15).json()
    tgt = next((c for c in chars if (c.get("count") or 0) > 0), None)
    assert tgt, "no character with products"
    slug = tgt["slug"]
    r = client.get(f"{BASE}/api/products", params={"character": slug}, timeout=15)
    assert r.status_code == 200
    total = int(r.headers.get("X-Total-Count", "0"))
    assert total == tgt["count"]
    for p in r.json():
        assert slug in (p.get("characters") or [])


def test_products_date_night_filter(client):
    r = client.get(f"{BASE}/api/products", params={"date_night": 1}, timeout=15)
    assert r.status_code == 200
    # Only assert endpoint accepts filter and returns int total
    int(r.headers.get("X-Total-Count", "0"))
