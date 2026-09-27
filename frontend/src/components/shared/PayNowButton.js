// components/shared/PayNowButton.js — tombol "Bayar Sekarang" (Midtrans Snap / mode simulasi). E14.
import React from 'react';
import { toast } from 'sonner';
import { CreditCard, Loader2, FlaskConical } from 'lucide-react';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog';
import { fetchPaymentConfig, startPayment, fetchPaymentStatus, mockPay, loadSnap } from '../../services/gateway';
import { formatIDR } from '../../lib/format';

function MockDialog({ open, onOpenChange, order, onOutcome, busy }) {
  const opts = [
    ['settlement', 'Bayar Berhasil', 'bg-emerald-600 hover:bg-emerald-700 text-white'],
    ['deny', 'Pembayaran Ditolak', 'bg-white text-rose-600 border border-rose-200 hover:bg-rose-50'],
    ['expire', 'Kedaluwarsa', 'bg-white text-black/70 border border-black/15 hover:bg-black/5'],
  ];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="cp-store max-w-md bg-[color:var(--cp-paper-warm)]" data-testid="mock-pay-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base"><FlaskConical className="h-4 w-4" /> Mode Simulasi Pembayaran</DialogTitle>
          <DialogDescription className="text-xs text-black/60">
            Midtrans belum terhubung (key belum diisi). Pilih hasil untuk menguji alur {order?.code} · {formatIDR(order?.total || 0)}.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          {opts.map(([k, label, cls]) => (
            <Button key={k} disabled={busy} onClick={() => onOutcome(k)} className={`rounded-full ${cls}`} data-testid={`mock-pay-${k}`}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : label}
            </Button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function PayNowButton({ order, accessToken, autoOpen = false, onChanged }) {
  const [busy, setBusy] = React.useState(false);
  const [mockOpen, setMockOpen] = React.useState(false);
  const opened = React.useRef(false);

  const refresh = React.useCallback(async () => {
    try { onChanged?.(await fetchPaymentStatus(order.code, accessToken)); } catch (e) { /* abaikan */ }
  }, [order.code, accessToken, onChanged]);

  const pay = React.useCallback(async () => {
    setBusy(true);
    try {
      const [cfg, tx] = await Promise.all([fetchPaymentConfig(), startPayment(order.code, accessToken)]);
      if (tx.mode === 'mock' || cfg.mode === 'mock') { setMockOpen(true); return; }
      const snap = await loadSnap(cfg);
      snap.pay(tx.token, {
        onSuccess: () => { toast.success('Pembayaran diterima, memverifikasi…'); refresh(); },
        onPending: () => { toast.message('Menunggu pembayaran Anda diselesaikan.'); refresh(); },
        onError: () => toast.error('Pembayaran gagal. Coba metode lain.'),
        onClose: () => refresh(),
      });
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message || 'Gagal memulai pembayaran');
    } finally { setBusy(false); }
  }, [order.code, accessToken, refresh]);

  React.useEffect(() => {
    if (autoOpen && !opened.current) { opened.current = true; pay(); }
  }, [autoOpen, pay]);

  const onOutcome = async (outcome) => {
    setBusy(true);
    try {
      onChanged?.(await mockPay(order.code, accessToken, outcome));
      setMockOpen(false);
      toast.success(outcome === 'settlement' ? 'Simulasi: pembayaran berhasil' : `Simulasi: ${outcome}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Simulasi gagal');
    } finally { setBusy(false); }
  };

  return (
    <>
      <Button onClick={pay} disabled={busy} className="rounded-full cp-btn-gold gap-2" data-testid="order-pay-now-button">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CreditCard className="h-4 w-4" />} Bayar Sekarang
      </Button>
      <MockDialog open={mockOpen} onOpenChange={setMockOpen} order={order} onOutcome={onOutcome} busy={busy} />
    </>
  );
}
