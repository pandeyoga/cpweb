"""services/email_templates.py — template email transaksional bermerek Collector Parfum (E15).

Fungsi mengembalikan (subject, html, text). HTML ber-inline-style + tabel agar aman di Gmail/Outlook.
Semua nilai dinamis di-escape.
"""
from datetime import datetime, timedelta, timezone
from html import escape

BRAND = "Collector Parfum"
INK, BRASS, PAPER, MUTED = "#1C1917", "#B89B6A", "#F7F3EC", "#78716C"
_WIB = timezone(timedelta(hours=7))
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def idr(n):
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


def wib(iso):
    d = datetime.fromisoformat(iso).astimezone(_WIB)
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}, {d:%H:%M} WIB"


def _e(v):
    return escape(str(v or ""))


def _button(label, link):
    return (f'<a href="{_e(link)}" style="display:inline-block;background:{INK};color:#fff;'
            f'text-decoration:none;padding:14px 28px;font-size:14px;letter-spacing:.08em;'
            f'text-transform:uppercase">{_e(label)}</a>')


def _layout(preheader, heading, body):
    return f"""<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(heading)}</title></head>
<body style="margin:0;background:{PAPER};font-family:Georgia,'Times New Roman',serif;color:{INK}">
<span style="display:none;max-height:0;overflow:hidden">{_e(preheader)}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER}"><tr><td align="center" style="padding:32px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#fff">
<tr><td style="background:{INK};padding:28px 32px;color:#fff;font-size:20px;letter-spacing:.3em;text-transform:uppercase">{BRAND}</td></tr>
<tr><td style="height:3px;background:{BRASS}"></td></tr>
<tr><td style="padding:36px 32px 8px"><h1 style="margin:0 0 16px;font-size:26px;font-weight:normal">{_e(heading)}</h1>{body}</td></tr>
<tr><td style="padding:24px 32px 32px;font-family:Arial,sans-serif;font-size:12px;color:{MUTED};border-top:1px solid #eee">
Email ini dikirim otomatis oleh {BRAND}. Mohon tidak membalas email ini.</td></tr>
</table></td></tr></table></body></html>"""


def _p(txt):
    return f'<p style="margin:0 0 16px;font-family:Arial,sans-serif;font-size:14px;line-height:1.6">{txt}</p>'


def _row(label, value, bold=False):
    w = "bold" if bold else "normal"
    return (f'<tr><td style="padding:6px 0;font-size:14px;font-weight:{w}">{label}</td>'
            f'<td align="right" style="padding:6px 0;font-size:14px;font-weight:{w}">{value}</td></tr>')


def _summary(order):
    rows = "".join(
        f'<tr><td style="padding:10px 0;border-bottom:1px solid #eee;font-size:14px">{_e(it.get("name"))}'
        f'<div style="color:{MUTED};font-size:12px">{_e(it.get("variant_type"))} × {int(it.get("quantity", 0))}</div></td>'
        f'<td align="right" style="padding:10px 0;border-bottom:1px solid #eee;font-size:14px">'
        f'{idr(int(it.get("unit_price", 0)) * int(it.get("quantity", 0)))}</td></tr>'
        for it in order.get("items", []))
    ship = order.get("shipping") or {}
    totals = _row("Subtotal", idr(order.get("subtotal")))
    totals += _row(f"Ongkir ({_e(ship.get('name'))})", idr(ship.get("price")))
    if int(order.get("discount", 0) or 0):
        totals += _row(f"Diskon {_e(order.get('voucher_code'))}", "− " + idr(order["discount"]))
    totals += _row("Total", idr(order.get("total")), bold=True)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="font-family:Arial,sans-serif;margin:8px 0 24px">{rows}{totals}</table>')


def _address(order):
    a = order.get("address") or {}
    parts = [a.get("street"), a.get("district"), a.get("city"), a.get("province"), a.get("postal_code")]
    line = ", ".join(_e(x) for x in parts if x)
    return (f'<div style="background:{PAPER};padding:16px;font-family:Arial,sans-serif;font-size:13px;'
            f'line-height:1.6;margin-bottom:24px"><strong>Dikirim ke</strong><br>{_e(a.get("name"))} · '
            f'{_e(a.get("phone"))}<br>{line}</div>')


def _text_items(order):
    lines = [f"- {it.get('name')} {it.get('variant_type', '')} x{it.get('quantity')}" for it in order.get("items", [])]
    return "\n".join(lines) + f"\nTotal: {idr(order.get('total'))}"


def paid_confirmation(order, link):
    code = order["code"]
    subject = f"Pembayaran diterima — Pesanan {code}"
    body = (_p(f"Terima kasih, {_e((order.get('address') or {}).get('name'))}! Pembayaran untuk pesanan "
               f"<strong>{_e(code)}</strong> sudah kami terima. Pesanan Anda segera kami siapkan.")
            + _summary(order) + _address(order)
            + f'<div style="margin:8px 0 28px">{_button("Lacak Pesanan", link)}</div>')
    html = _layout(f"Pembayaran {idr(order.get('total'))} untuk {code} diterima.", "Pembayaran Diterima", body)
    text = (f"Terima kasih! Pembayaran pesanan {code} sudah kami terima.\n\n{_text_items(order)}\n\n"
            f"Lacak pesanan: {link}\n\n— {BRAND}")
    return subject, html, text


def payment_reminder(order, link, hours_left):
    code, deadline = order["code"], wib(order["payment_deadline"])
    left = f"{int(hours_left)} jam" if hours_left >= 1 else f"{max(int(hours_left * 60), 1)} menit"
    subject = f"Sisa {left} lagi — selesaikan pembayaran {code}"
    body = (_p(f"Pesanan <strong>{_e(code)}</strong> masih menunggu pembayaran. Selesaikan sebelum "
               f"<strong>{deadline}</strong> (sekitar {left} lagi) agar pesanan tidak dibatalkan otomatis "
               f"dan stok tetap untuk Anda.")
            + _summary(order)
            + f'<div style="margin:8px 0 28px">{_button("Bayar Sekarang", link)}</div>')
    html = _layout(f"Sisa {left} untuk membayar pesanan {code}.", "Jangan Sampai Terlewat", body)
    text = (f"Pesanan {code} menunggu pembayaran. Batas bayar: {deadline} (sekitar {left} lagi).\n\n"
            f"{_text_items(order)}\n\nBayar sekarang: {link}\n\n— {BRAND}")
    return subject, html, text


def _resi_box(sh):
    return (f'<div style="border:1px solid {BRASS};padding:18px;margin:0 0 20px;font-family:Arial,sans-serif">'
            f'<div style="font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:{MUTED}">Nomor Resi · '
            f'{_e(sh.get("courier_name"))}</div><div style="font-family:\'Courier New\',monospace;font-size:24px;'
            f'font-weight:bold;letter-spacing:.06em;margin-top:6px">{_e(sh.get("tracking_number"))}</div></div>')


def order_shipped(order, link, correction=False):
    code, sh = order["code"], order.get("shipment") or {}
    eta = (order.get("shipping") or {}).get("eta")
    intro = (f"Ada pembaruan nomor resi untuk pesanan <strong>{_e(code)}</strong>. Mohon gunakan resi di bawah ini."
             if correction else
             f"Kabar baik! Pesanan <strong>{_e(code)}</strong> sudah kami serahkan ke kurir dan sedang dalam perjalanan.")
    subject = (f"Pembaruan resi — Pesanan {code}" if correction else f"Pesanan {code} sedang dikirim")
    body = (_p(intro) + _resi_box(sh)
            + _p(f"Kurir: <strong>{_e(sh.get('courier_name'))}</strong>" + (f" · Estimasi tiba {_e(eta)}" if eta else "")
                 + "<br>Salin nomor resi di atas, lalu tempel di halaman lacak kurir.")
            + f'<div style="margin:4px 0 24px">{_button("Lacak Paket", sh.get("tracking_url"))}'
            + f'&nbsp;&nbsp;<a href="{_e(link)}" style="font-family:Arial,sans-serif;font-size:13px;color:{INK}">'
            + 'Lihat Pesanan</a></div>'
            + _summary(order) + _address(order))
    heading = "Resi Diperbarui" if correction else "Pesanan Dikirim"
    html = _layout(f"Resi {sh.get('courier_name')} {sh.get('tracking_number')} untuk {code}.", heading, body)
    text = (f"{'Pembaruan resi' if correction else 'Pesanan sedang dikirim'} — {code}\n"
            f"Kurir: {sh.get('courier_name')}\nNomor resi: {sh.get('tracking_number')}\n"
            f"Lacak paket: {sh.get('tracking_url')}\nLihat pesanan: {link}\n\n{_text_items(order)}\n\n— {BRAND}")
    return subject, html, text
