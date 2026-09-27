"""services/net_guard.py — unduh URL eksternal secara aman (anti SSRF + batas ukuran stream)."""
import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

MAX_REDIRECTS = 3


class UnsafeUrl(Exception):
    pass


async def _assert_public(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeUrl("URL harus http:// atau https:// dengan host yang sah")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise UnsafeUrl("Host URL tidak dapat ditemukan")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeUrl("URL mengarah ke alamat internal/privat — ditolak")


async def fetch_public(url: str, max_bytes: int, headers=None, timeout=25.0):
    """GET url publik: tiap redirect divalidasi ulang, body dibaca bertahap & dihentikan saat > max_bytes.
    Return (status_code, content_type, data). Raise UnsafeUrl / ValueError (terlalu besar)."""
    current = url
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await _assert_public(current)
            async with client.stream("GET", current, headers=headers or {}) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    current = urljoin(current, resp.headers["location"])
                    continue
                declared = int(resp.headers.get("content-length") or 0)
                if declared > max_bytes:
                    raise ValueError("too_large")
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        raise ValueError("too_large")
                ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                return resp.status_code, ctype, bytes(buf)
    raise UnsafeUrl("Terlalu banyak redirect")
