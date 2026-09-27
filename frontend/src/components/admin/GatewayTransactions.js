// components/admin/GatewayTransactions.js — monitor transaksi Midtrans + tombol refund (E14).
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Loader2, Undo2 } from 'lucide-react';
import { listPaymentTransactions, refundOrder } from '../../services/admin';
import { formatIDR } from '../../lib/format';
import { EmptyState, TableSkeleton, formatDateTime } from './adminUi';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Card, CardContent } from '../ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';

const TX_META = {
  pending: ['Menunggu', 'bg-amber-100 text-amber-800'],
  paid: ['Lunas', 'bg-emerald-100 text-emerald-800'],
  expired: ['Kedaluwarsa', 'bg-slate-100 text-slate-700'],
  failed: ['Gagal', 'bg-rose-100 text-rose-800'],
  refund: ['Refund', 'bg-violet-100 text-violet-800'],
  partial_refund: ['Refund Sebagian', 'bg-violet-100 text-violet-800'],
};

export const TxBadge = ({ status }) => {
  const [label, cls] = TX_META[status] || [status, 'bg-black/5'];
  return <Badge variant="outline" className={`border-0 ${cls}`}>{label}</Badge>;
};

export const RefundButton = ({ order, onDone }) => {
  const [busy, setBusy] = useState(false);
  const refundable = Number(order.paid_amount || 0) - Number(order.refunded_amount || 0);
  if (order.payment?.group !== 'online' || refundable <= 0) return null;
  const run = async () => {
    const reason = window.prompt(`Refund penuh ${formatIDR(refundable)} untuk ${order.code}? Tulis alasan:`, 'Permintaan pelanggan');
    if (reason === null) return;
    setBusy(true);
    try {
      const res = await refundOrder(order.code, { reason });
      toast.success('Refund diproses'); onDone?.(res);
    } catch (e) { toast.error(e?.response?.data?.detail || 'Refund gagal'); } finally { setBusy(false); }
  };
  return (
    <Button variant="outline" className="w-full gap-2 border-violet-200 text-violet-700" onClick={run} disabled={busy} data-testid="admin-order-refund-button">
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Undo2 className="h-4 w-4" />} Refund {formatIDR(refundable)}
    </Button>
  );
};

export default function GatewayTransactions() {
  const [rows, setRows] = useState(null);
  useEffect(() => { listPaymentTransactions().then(setRows).catch(() => setRows([])); }, []);
  return (
    <Card className="border-border/70 mb-6" data-testid="admin-gateway-transactions"><CardContent className="p-4">
      <div className="mb-3 text-sm font-semibold">Transaksi Online (Midtrans)</div>
      {rows === null ? <TableSkeleton rows={4} cols={5} /> : rows.length === 0 ? (
        <EmptyState title="Belum ada transaksi online" hint="Transaksi Midtrans akan tampil di sini." />
      ) : (
        <div className="overflow-x-auto"><Table>
          <TableHeader><TableRow>
            <TableHead>Waktu</TableHead><TableHead>Pesanan</TableHead><TableHead>ID Midtrans</TableHead>
            <TableHead>Metode</TableHead><TableHead className="text-right">Nominal</TableHead><TableHead>Status</TableHead>
          </TableRow></TableHeader>
          <TableBody>{rows.map((r) => (
            <TableRow key={r.id} data-testid="admin-gateway-tx-row">
              <TableCell className="text-xs">{formatDateTime(r.created_at)}</TableCell>
              <TableCell><Link className="underline" to={`/admin/pesanan/${r.order_code}`}>{r.order_code}</Link></TableCell>
              <TableCell className="font-mono text-xs">{r.gateway_order_id}{r.mode === 'mock' ? ' · SIMULASI' : ''}</TableCell>
              <TableCell className="text-xs">{r.payment_type || '—'}</TableCell>
              <TableCell className="text-right">{formatIDR(r.gross_amount)}</TableCell>
              <TableCell>
                <TxBadge status={r.status} />
                {r.needs_refund ? (
                  <Button size="sm" variant="outline" className="ml-2 h-6 px-2 text-[10px] text-rose-600" data-testid="admin-gateway-tx-refund"
                    onClick={() => refundOrder(r.order_code, { reason: 'Dibayar setelah pesanan batal' })
                      .then(() => { toast.success('Refund diproses'); return listPaymentTransactions().then(setRows); })
                      .catch((e) => toast.error(e?.response?.data?.detail || 'Refund gagal'))}>
                    Refund (dibayar setelah batal)
                  </Button>
                ) : null}
              </TableCell>
            </TableRow>
          ))}</TableBody>
        </Table></div>
      )}
    </CardContent></Card>
  );
}
