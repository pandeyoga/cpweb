// components/shared/PaymentDeadline.js — batas bayar + hitung mundur (SALES-06/17).
import React from 'react';
import { Clock } from 'lucide-react';

const pad = (n) => String(n).padStart(2, '0');

export const formatDeadline = (iso) => new Date(iso).toLocaleString('id-ID', {
  day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
});

export default function PaymentDeadline({ deadline, compact = false }) {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!deadline) return null;
  const left = Math.max(0, new Date(deadline).getTime() - now);
  const h = Math.floor(left / 3600000);
  const m = Math.floor((left % 3600000) / 60000);
  const s = Math.floor((left % 60000) / 1000);
  const over = left === 0;
  if (compact) {
    return (
      <span className="cp-mono text-[10px] text-amber-700" data-testid="order-payment-deadline-compact">
        {over ? 'Batas bayar lewat' : `Bayar sebelum ${formatDeadline(deadline)}`}
      </span>
    );
  }
  return (
    <div className="flex items-center gap-2 text-sm text-amber-800" data-testid="order-payment-deadline">
      <Clock className="h-4 w-4" />
      {over ? (
        <span>Batas pembayaran telah lewat — pesanan akan dibatalkan otomatis.</span>
      ) : (
        <span>
          Bayar sebelum <b>{formatDeadline(deadline)}</b> · sisa{' '}
          <span className="cp-mono font-semibold" data-testid="order-payment-countdown">{pad(h)}:{pad(m)}:{pad(s)}</span>
        </span>
      )}
    </div>
  );
}
