// components/admin/EmailLogs.js — log email transaksional (konfirmasi lunas + pengingat bayar) (E15).
import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Eye, Loader2, Mail, RotateCw } from 'lucide-react';
import { getEmailLog, listEmailLogs, resendEmail } from '../../services/admin';
import { EmptyState, TableSkeleton, formatDateTime } from './adminUi';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Card, CardContent } from '../ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';

const KIND = { paid_confirmation: 'Konfirmasi Lunas', reminder_12h: 'Pengingat 12 jam', reminder_2h: 'Pengingat 2 jam',
  shipped: 'Pesanan Dikirim', shipped_update: 'Pembaruan Resi' };
const STATUS = {
  sent: ['Terkirim', 'bg-emerald-100 text-emerald-800'],
  mocked: ['Simulasi', 'bg-sky-100 text-sky-800'],
  failed: ['Gagal', 'bg-rose-100 text-rose-800'],
  skipped: ['Dilewati', 'bg-slate-100 text-slate-700'],
};
const MODE_NOTE = {
  mock: 'MODE SIMULASI — email tidak benar-benar dikirim, hanya dicatat. Isi SMTP di backend/.env untuk mengaktifkan.',
  off: 'SMTP belum dikonfigurasi — email tidak dikirim.',
};

const StatusBadge = ({ s }) => {
  const [label, cls] = STATUS[s] || [s, 'bg-black/5'];
  return <Badge variant="outline" className={`border-0 ${cls}`}>{label}</Badge>;
};

const Preview = ({ log, onClose }) => (
  <Dialog open={!!log} onOpenChange={(o) => !o && onClose()}>
    <DialogContent className="max-w-3xl" data-testid="admin-email-preview-dialog">
      <DialogHeader><DialogTitle className="text-base">{log?.subject}</DialogTitle></DialogHeader>
      <div className="text-xs text-muted-foreground">Kepada: {log?.to}{log?.error ? ` · ${log.error}` : ''}</div>
      <iframe title="Pratinjau email" sandbox="" srcDoc={log?.html || ''} className="h-[65vh] w-full border" data-testid="admin-email-preview-frame" />
    </DialogContent>
  </Dialog>
);

const Row = ({ r, onPreview, onResend, busy }) => (
  <TableRow data-testid="admin-email-log-row">
    <TableCell className="text-xs">{formatDateTime(r.created_at)}</TableCell>
    <TableCell className="text-xs">{KIND[r.kind] || r.kind}</TableCell>
    <TableCell className="text-xs">{r.to}</TableCell>
    <TableCell>{r.order_code ? <Link className="underline" to={`/admin/pesanan/${r.order_code}`}>{r.order_code}</Link> : '—'}</TableCell>
    <TableCell><StatusBadge s={r.status} /></TableCell>
    <TableCell className="whitespace-nowrap text-right">
      <Button size="sm" variant="ghost" className="h-7 gap-1 px-2" onClick={() => onPreview(r.id)} data-testid="admin-email-preview-button"><Eye className="h-3.5 w-3.5" /> Lihat</Button>
      <Button size="sm" variant="ghost" className="h-7 gap-1 px-2" onClick={() => onResend(r.id)} disabled={busy === r.id} data-testid="admin-email-resend-button">
        {busy === r.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCw className="h-3.5 w-3.5" />} Kirim ulang
      </Button>
    </TableCell>
  </TableRow>
);

export default function EmailLogs() {
  const [data, setData] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(null);
  const load = useCallback(() => listEmailLogs().then(setData).catch(() => setData({ items: [] })), []);
  useEffect(() => { load(); }, [load]);
  const openPreview = (id) => getEmailLog(id).then(setPreview).catch(() => toast.error('Gagal memuat email'));
  const resend = async (id) => {
    setBusy(id);
    try {
      const r = await resendEmail(id);
      toast[r.status === 'failed' ? 'error' : 'success'](r.status === 'failed' ? `Gagal: ${r.error}` : 'Email dikirim ulang');
      await load();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Gagal kirim ulang'); } finally { setBusy(null); }
  };
  return (
    <Card className="border-border/70 mb-6" data-testid="admin-email-logs"><CardContent className="p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><Mail className="h-4 w-4" /> Email ke Pembeli
        {data?.from_email ? <span className="font-normal text-xs text-muted-foreground">dari {data.from_email}</span> : null}</div>
      {MODE_NOTE[data?.mode] ? <div className="mb-3 rounded bg-amber-50 px-3 py-2 text-xs text-amber-900" data-testid="admin-email-mode-note">{MODE_NOTE[data.mode]}</div> : null}
      {data === null ? <TableSkeleton rows={4} cols={6} /> : data.items.length === 0 ? (
        <EmptyState title="Belum ada email" hint="Konfirmasi lunas & pengingat batas bayar akan tercatat di sini." />
      ) : (
        <div className="overflow-x-auto"><Table>
          <TableHeader><TableRow>
            <TableHead>Waktu</TableHead><TableHead>Jenis</TableHead><TableHead>Penerima</TableHead>
            <TableHead>Pesanan</TableHead><TableHead>Status</TableHead><TableHead />
          </TableRow></TableHeader>
          <TableBody>{data.items.map((r) => <Row key={r.id} r={r} onPreview={openPreview} onResend={resend} busy={busy} />)}</TableBody>
        </Table></div>
      )}
      <Preview log={preview} onClose={() => setPreview(null)} />
    </CardContent></Card>
  );
}
