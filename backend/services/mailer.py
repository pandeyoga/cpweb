"""services/mailer.py — kirim email via SMTP (akun fastcloud.id) + catat ke `email_logs` (E15).

Mode (dari env, dievaluasi tiap panggilan):
  - live : SMTP_HOST + SMTP_USERNAME + SMTP_PASSWORD terisi → kirim sungguhan.
  - mock : kredensial kosong + EMAIL_MOCK=true → TIDAK dikirim; dicatat (bisa dipratinjau admin).
  - off  : selain itu → dicatat `skipped`.
Port 465 = SSL langsung; port lain (587) = STARTTLS.
"""
import asyncio
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from core_utils import new_id, now_iso

_TRUE = ("1", "true", "yes", "on")


def _env(k):
    return (os.environ.get(k) or "").strip()


def mode():
    if _env("SMTP_HOST") and _env("SMTP_USERNAME") and _env("SMTP_PASSWORD"):
        return "live"
    return "mock" if _env("EMAIL_MOCK").lower() in _TRUE else "off"


def sender():
    return _env("SMTP_FROM_NAME"), _env("SMTP_FROM_EMAIL") or _env("SMTP_USERNAME")


def _send_sync(to, subject, html, text):
    name, addr = sender()
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, formataddr((name, addr)), to
    msg["Message-ID"] = make_msgid(domain=addr.split("@")[-1] or None)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    host, port = _env("SMTP_HOST"), int(_env("SMTP_PORT") or 465)
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20, context=ctx) as s:
            s.login(_env("SMTP_USERNAME"), _env("SMTP_PASSWORD"))
            s.send_message(msg)
        return
    with smtplib.SMTP(host, port, timeout=20) as s:
        s.starttls(context=ctx)
        s.login(_env("SMTP_USERNAME"), _env("SMTP_PASSWORD"))
        s.send_message(msg)


async def send(db, *, kind, to, subject, html, text, order_code=None):
    """Kirim (atau simulasikan) lalu catat. Tak pernah melempar — status ada di log."""
    m = mode()
    log = {"id": new_id("eml"), "kind": kind, "to": to, "subject": subject, "order_code": order_code,
           "mode": m, "status": "skipped", "error": None, "html": html[:200000], "text": text[:50000],
           "created_at": now_iso()}
    if not to:
        log["error"] = "Alamat email kosong"
    elif m == "live":
        try:
            await asyncio.to_thread(_send_sync, to, subject, html, text)
            log["status"] = "sent"
        except (smtplib.SMTPException, OSError, ValueError) as e:
            log.update(status="failed", error=str(e)[:300])
    elif m == "mock":
        log["status"] = "mocked"
    else:
        log["error"] = "SMTP belum dikonfigurasi"
    await db.email_logs.insert_one(dict(log))
    return log
