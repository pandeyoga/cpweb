"""external_urls.py — SSOT endpoint layanan eksternal (override via environment).

Semua URL pihak ketiga dibaca dari env dengan fallback default sehingga TIDAK ada
hardcode URL di `routers/` maupun `services/` (kepatuhan CHECK 3 validate_compliance).
"""
import os

GOOGLE_PLACES_URL = os.environ.get(
    "GOOGLE_PLACES_URL",
    "https://maps.googleapis.com/maps/api/place/details/json",
)

# Halaman lacak resmi kurir (E16). Kurir tak dikenal → FALLBACK dengan resi terisi.
COURIER_TRACK_URLS = {
    "jne": os.environ.get("TRACK_URL_JNE", "https://www.jne.co.id/tracking-package"),
    "jnt": os.environ.get("TRACK_URL_JNT", "https://jet.co.id/track"),
    "sicepat": os.environ.get("TRACK_URL_SICEPAT", "https://www.sicepat.com/checkAwb"),
    "anteraja": os.environ.get("TRACK_URL_ANTERAJA", "https://anteraja.id/tracking"),
}
COURIER_FALLBACK_URL = os.environ.get("TRACK_URL_FALLBACK", "https://cekresi.com/?noresi={resi}")
