import React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { CheckCircle2, ArrowRight, MapPin, Truck, Loader2, Copy, Landmark, Wallet, Banknote, Clock, XCircle } from 'lucide-react';
import { Button } from '../components/ui/button';
import { formatIDR } from '../lib/format';
import { fetchOrder, orderStatusLabel, isAwaitingPayment } from '../services/orders';
import PaymentDeadline from '../components/shared/PaymentDeadline';
import PayNowButton from '../components/shared/PayNowButton';
import PaymentPanel from '../components/shared/PaymentPanel';
import { toast } from 'sonner';

function PaymentInstructions({ order }) {
  const grp = order?.payment?.group;
  if (!grp) return null;
  const name = order.payment?.name || '';
  const content = {
    transfer: {
      icon: Landmark,
      title: 'Instruksi Pembayaran — Transfer',
      body: `Silakan transfer sebesar ${formatIDR(order.total)} ke rekening ${name || 'bank kami'}. Setelah transfer, konfirmasi via WhatsApp agar pesanan diproses.`,
    },
    ewallet: {
      icon: Wallet,
      title: 'Instruksi Pembayaran — E-Wallet',
      body: `Lakukan pembayaran ${formatIDR(order.total)} melalui ${name || 'e-wallet'} ke nomor merchant kami, lalu konfirmasi.`,
    },
    cod: {
      icon: Banknote,
      title: 'Bayar di Tempat (COD)',
      body: `Siapkan uang tunai sebesar ${formatIDR(order.total)} (termasuk biaya COD) saat kurir tiba.`,
    },
  }[grp];
  if (!content) return null;
  const Icon = content.icon;
  return (
    <div className="px-6 py-4 border-b border-black/10 bg-[color:var(--cp-market-blue-soft)]/40" data-testid="order-payment-instructions">
      <div className="flex items-start gap-3">
        <Icon className="h-4 w-4 text-[color:var(--cp-market-blue)] mt-0.5" />
        <div>
          <div className="text-sm font-semibold">{content.title}</div>
          <div className="text-xs text-black/70 mt-1 leading-relaxed">{content.body}</div>
        </div>
      </div>
    </div>
  );
}

function ShipmentInfo({ shipment }) {
  if (!shipment?.tracking_number) return null;
  const copy = () => navigator.clipboard?.writeText(shipment.tracking_number).then(() => toast.success('Nomor resi disalin'));
  return (
    <div className="px-6 py-4 border-b border-black/10 flex flex-wrap items-center justify-between gap-3" data-testid="order-shipment-info">
      <div>
        <div className="cp-mono uppercase text-[10px] tracking-[0.22em] text-black/60">Nomor Resi · {shipment.courier_name}</div>
        <button onClick={copy} className="cp-mono text-lg font-semibold inline-flex items-center gap-2 hover:text-[color:var(--cp-market-blue)]" data-testid="order-tracking-number">
          {shipment.tracking_number} <Copy className="h-3.5 w-3.5 opacity-60" />
        </button>
      </div>
      <a href={shipment.tracking_url} target="_blank" rel="noreferrer" data-testid="order-tracking-link"
        className="inline-flex items-center gap-2 rounded-full bg-black text-white px-5 py-2 text-xs uppercase tracking-[0.18em] hover:bg-black/80">
        <Truck className="h-3.5 w-3.5" /> Lacak Paket
      </a>
    </div>
  );
}

// Hero status-aware (SALES-17): jangan klaim "dibayar" sebelum uang masuk.
const HERO = {
  waiting: { icon: Clock, cls: 'bg-amber-100 text-amber-700', eyebrow: 'Pesanan Dibuat', title: 'Menunggu pembayaran.',
    body: 'Pesanan Anda sudah kami terima. Selesaikan pembayaran sebelum batas waktu agar pesanan diproses.' },
  paid: { icon: CheckCircle2, cls: 'bg-[color:var(--cp-market-blue-soft)] text-[color:var(--cp-market-blue)]', eyebrow: 'Pembayaran Diterima', title: 'Terima kasih!',
    body: 'Pembayaran sudah kami terima. Pesanan Anda segera kami proses & kirim.' },
  shipped: { icon: Truck, cls: 'bg-[color:var(--cp-market-blue-soft)] text-[color:var(--cp-market-blue)]', eyebrow: 'Pesanan Dikirim', title: 'Dalam perjalanan.',
    body: 'Pesanan Anda sudah diserahkan ke kurir. Lacak paket dengan nomor resi di bawah.' },
  cancelled: { icon: XCircle, cls: 'bg-rose-100 text-rose-700', eyebrow: 'Pesanan Dibatalkan', title: 'Pesanan dibatalkan.',
    body: 'Pesanan ini sudah dibatalkan. Silakan buat pesanan baru bila masih ingin membeli.' },
};
const heroKey = (o) => (!o || isAwaitingPayment(o) || o.status === 'pending' ? 'waiting' : o.status === 'cancelled' ? 'cancelled' : o.status === 'shipped' ? 'shipped' : 'paid');

export default function OrderSuccessPage() {
  const [params] = useSearchParams();
  const fromStore = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const code = params.get('code') || fromStore('cp:lastOrderCode');
  const token = params.get('t') || (code === fromStore('cp:lastOrderCode') ? fromStore('cp:lastOrderToken') : null);
  const [order, setOrder] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  const reload = React.useCallback(async () => {
    if (!code) return;
    try { setOrder(await fetchOrder(code, token)); } catch (e) { /* keep current */ }
  }, [code, token]);

  React.useEffect(() => {
    window.scrollTo({ top: 0 });
    if (code) {
      try {
        localStorage.setItem('cp:lastOrderCode', code);
        if (token) localStorage.setItem('cp:lastOrderToken', token); else localStorage.removeItem('cp:lastOrderToken');
      } catch (e) {}
    }
    let active = true;
    (async () => {
      if (!code) { setLoading(false); setError('notfound'); return; }
      try {
        const o = await fetchOrder(code, token);
        if (active) {
          setOrder(o);
          // Event `purchase` kini dicatat server saat order LUNAS (SALES-14) — bukan saat halaman dibuka.
        }
      } catch (e) {
        if (active) setError('notfound');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [code, token]);

  const hk = heroKey(order);
  const hero = HERO[hk];
  const HeroIcon = hero.icon;

  const copyCode = () => {
    try { navigator.clipboard.writeText(order.code); toast.success('Nomor pesanan disalin'); } catch (e) {}
  };

  return (
    <div className="cp-container cp-section" data-testid="order-success-page">
      <div className="max-w-2xl mx-auto">
        <motion.div initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }} className="flex items-center justify-center">
          <div className={`h-20 w-20 rounded-full flex items-center justify-center ${hero.cls}`}>
            <HeroIcon className="h-10 w-10" />
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, duration: 0.6 }} className="text-center mt-6" data-testid="order-success-hero" data-state={hk}>
          <div className="cp-mono uppercase text-[11px] tracking-[0.22em] text-black/60">{hero.eyebrow}</div>
          <h1 className="cp-headline text-4xl sm:text-5xl mt-2" data-testid="order-success-title">{hero.title}</h1>
          <p className="text-sm sm:text-base text-black/70 mt-3 max-w-md mx-auto">{hero.body}</p>
          {order && isAwaitingPayment(order) && (
            <div className="mt-4 flex flex-col items-center gap-3">
              <div className="inline-flex rounded-full bg-amber-50 border border-amber-200 px-4 py-2">
                <PaymentDeadline deadline={order.payment_deadline} />
              </div>
              {order.payment?.group === 'online' && (
                <PayNowButton order={order} accessToken={token} autoOpen={params.get('pay') === '1'} onChanged={setOrder} />
              )}
            </div>
          )}
        </motion.div>

        {loading && (
          <div className="mt-10 flex items-center justify-center py-10 text-black/50">
            <Loader2 className="h-5 w-5 animate-spin mr-2" /> Memuat pesanan…
          </div>
        )}

        {!loading && error && (
          <div className="mt-10 rounded-2xl border border-black/10 bg-[color:var(--cp-paper-warm)] p-8 text-center" data-testid="order-success-notfound">
            <div className="text-sm text-black/70">Detail pesanan tidak dapat ditampilkan. Simpan nomor pesanan Anda untuk pengecekan.</div>
            {code && <div className="cp-mono text-lg font-semibold mt-2" data-testid="order-success-code">{code}</div>}
          </div>
        )}

        {!loading && order && (
          <div className="mt-10 rounded-2xl border border-black/10 bg-[color:var(--cp-paper-warm)] overflow-hidden">
            <div className="px-6 py-4 border-b border-black/10 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="cp-mono uppercase text-[10px] tracking-[0.22em] text-black/60">Nomor Pesanan</div>
                <button onClick={copyCode} className="cp-mono text-lg font-semibold inline-flex items-center gap-2 hover:text-[color:var(--cp-market-blue)]" data-testid="order-success-code">
                  {order.code} <Copy className="h-3.5 w-3.5 opacity-60" />
                </button>
                <div className="mt-1">
                  <span className="cp-mono uppercase text-[10px] tracking-[0.2em] bg-[color:var(--cp-paper-fog)] px-2 py-0.5 rounded-full" data-testid="order-success-status">
                    {orderStatusLabel(order)}
                  </span>
                </div>
              </div>
              <div className="text-right">
                <div className="cp-mono uppercase text-[10px] tracking-[0.22em] text-black/60">{order.payment_status === 'lunas' ? 'Total Dibayar' : 'Total Tagihan'}</div>
                <div className="cp-mono text-lg font-semibold" data-testid="order-success-total">{formatIDR(order.total)}</div>
              </div>
            </div>

            <PaymentInstructions order={order} />

            <PaymentPanel order={order} onRefresh={reload} />

            <div className="px-6 py-4 border-b border-black/10 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="flex items-start gap-2">
                <MapPin className="h-4 w-4 text-black/60 mt-0.5" />
                <div>
                  <div className="cp-mono uppercase text-[10px] tracking-[0.22em] text-black/60">Dikirim Ke</div>
                  <div className="text-sm font-medium">{order.address?.name}</div>
                  <div className="text-xs text-black/70">{order.address?.street}, {order.address?.city}</div>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <Truck className="h-4 w-4 text-black/60 mt-0.5" />
                <div>
                  <div className="cp-mono uppercase text-[10px] tracking-[0.22em] text-black/60">Metode Kirim</div>
                  <div className="text-sm font-medium">{order.shipping?.name}</div>
                  <div className="text-xs text-black/70">Estimasi {order.shipping?.eta}</div>
                </div>
              </div>
            </div>

            <ShipmentInfo shipment={order.shipment} />

            <div className="px-6 py-4">
              <div className="cp-mono uppercase text-[10px] tracking-[0.22em] text-black/60 mb-3">Ringkasan Item</div>
              <div className="space-y-3">
                {order.items.map((it) => (
                  <div key={it.key} className="flex items-center gap-3">
                    <div className="h-12 w-10 rounded-md overflow-hidden bg-[color:var(--cp-paper-fog)] flex-shrink-0">
                      <img src={it.image} alt={it.name} className="h-full w-full object-cover" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate">{it.name}</div>
                      <div className="cp-mono text-[10px] uppercase tracking-[0.22em] text-black/55">{it.variantLabel || `${it.concentration ? it.concentration + ' · ' : ''}${it.variantType ? it.variantType + ' · ' : ''}${it.volumeMl}ml`} · x{it.quantity}</div>
                    </div>
                    <div className="cp-mono text-sm">{formatIDR(it.unitPrice * it.quantity)}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link to="/akun">
            <Button variant="outline" className="rounded-full" data-testid="order-success-view-orders">Lihat Pesanan Saya</Button>
          </Link>
          <Link to="/shop">
            <Button className="rounded-full bg-[color:var(--cp-ink)] text-[color:var(--cp-paper)] hover:bg-black" data-testid="order-success-continue-shopping">
              Lanjut Belanja <ArrowRight className="h-4 w-4 ml-2" />
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
