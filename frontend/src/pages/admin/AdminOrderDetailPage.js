// pages/admin/AdminOrderDetailPage.js — detail + ubah status via transition (BR-6, INV-M3).
import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, ExternalLink, Pencil } from 'lucide-react';
import { getOrder, setOrderStatus, updateShipment } from '../../services/admin';
import { formatIDR } from '../../lib/format';
import {
  PageHeader, StatusBadge, formatDateTime, ORDER_STATUS_META,
} from '../../components/admin/adminUi';
import { adminTestIds as T } from '../../constants/testIds/admin';
import { RefundButton } from '../../components/admin/GatewayTransactions';
import ShipDialog from '../../components/admin/ShipDialog';
import { Button } from '../../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../../components/ui/table';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../../components/ui/select';
import {
  AlertDialog, AlertDialogTrigger, AlertDialogContent, AlertDialogHeader, AlertDialogTitle,
  AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction,
} from '../../components/ui/alert-dialog';

const Row = ({ label, value }) => (
  <div className="flex justify-between gap-4 text-sm py-1">
    <span className="text-muted-foreground">{label}</span><span className="text-right">{value}</span>
  </div>
);

export default function AdminOrderDetailPage() {
  const { code } = useParams();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [ship, setShip] = useState(null); // null | 'ship' | 'edit'
  const [selKey, setSelKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try { setOrder(await getOrder(code)); }
    catch (e) { toast.error('Pesanan tidak ditemukan.'); navigate('/admin/pesanan'); }
    finally { setLoading(false); }
  }, [code, navigate]);
  useEffect(() => { load(); }, [load]);

  const change = async (to, extra) => {
    if (to === 'shipped' && !extra) { setShip('ship'); setSelKey((k) => k + 1); return; } // resi wajib (E16)
    setBusy(true);
    try { const updated = await setOrderStatus(code, to, extra); setOrder(updated); toast.success(`Status → ${ORDER_STATUS_META[to]?.label || to}`); }
    catch (e) { toast.error(e?.response?.data?.detail || 'Transisi status tidak diizinkan.'); throw e; }
    finally { setBusy(false); }
  };
  const submitShip = async (courier, resi) => {
    if (ship === 'ship') return change('shipped', { courier, tracking_number: resi });
    try { setOrder(await updateShipment(code, courier, resi)); toast.success('Resi diperbarui — email dikirim ke pembeli'); }
    catch (e) { toast.error(e?.response?.data?.detail || 'Gagal menyimpan resi'); throw e; }
  };

  if (loading) return <div className="h-64 grid place-items-center text-muted-foreground">Memuat pesanan…</div>;
  if (!order) return null;

  // SALES-18: transisi sah dari backend (SSOT services/orders.LEGAL_TRANSITIONS).
  const allowed = order.allowed_transitions || [];
  const nextOptions = allowed.filter((s) => s !== 'cancelled');
  const canCancel = allowed.includes('cancelled');

  return (
    <div>
      <PageHeader
        title={`Pesanan ${order.code}`}
        description={formatDateTime(order.created_at)}
        actions={<Button variant="secondary" onClick={() => navigate('/admin/pesanan')} className="gap-2"><ArrowLeft className="h-4 w-4" /> Kembali</Button>}
      />

      <div className="grid lg:grid-cols-3 gap-6 items-start">
        <Card className="lg:col-span-2 border-border/70">
          <CardHeader><CardTitle className="text-base">Item</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <TableHeader><TableRow>
                <TableHead>Produk</TableHead><TableHead>Varian</TableHead><TableHead className="text-center">Qty</TableHead>
                <TableHead className="text-right">Harga</TableHead><TableHead className="text-right">Subtotal</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {(order.items || []).map((it, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-medium">{it.name}</TableCell>
                    <TableCell className="font-[\'Azeret_Mono\',monospace] text-xs">{(it.options && Object.values(it.options).filter(Boolean).join(' / ')) || `${it.variant_type ? `${it.variant_type} · ` : ''}${it.volume_ml}ml`}{it.sku ? ` · ${it.sku}` : ''}</TableCell>
                    <TableCell className="text-center">{it.quantity}</TableCell>
                    <TableCell className="text-right font-[\'Azeret_Mono\',monospace] text-sm">{formatIDR(it.unit_price || 0)}</TableCell>
                    <TableCell className="text-right font-[\'Azeret_Mono\',monospace] text-sm">{formatIDR((it.unit_price || 0) * (it.quantity || 0))}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="mt-4 max-w-xs ml-auto">
              <Row label="Subtotal" value={formatIDR(order.subtotal || 0)} />
              <Row label="Ongkir" value={formatIDR(order.shipping?.price ?? order.shipping_cost ?? 0)} />
              {order.discount ? <Row label="Diskon" value={`- ${formatIDR(order.discount)}`} /> : null}
              {order.cod_fee ? <Row label="Biaya COD" value={formatIDR(order.cod_fee)} /> : null}
              <div className="border-t border-border mt-1 pt-1 flex justify-between font-semibold">
                <span>Total</span><span className="font-[\'Azeret_Mono\',monospace]">{formatIDR(order.total || 0)}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card className="border-border/70">
            <CardHeader><CardTitle className="text-base">Status & Proses</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2"><span className="text-sm text-muted-foreground">Saat ini:</span><StatusBadge status={order.status} /></div>
              <div className="text-xs text-muted-foreground" data-testid="admin-order-payment-info">
                Pembayaran: {order.payment_status || '—'}{order.refunded_amount ? ` · direfund ${formatIDR(order.refunded_amount)}` : ''}
                {order.cancel_reason ? ` · alasan batal: ${order.cancel_reason}` : ''}
              </div>
              <RefundButton order={order} onDone={setOrder} />
              {nextOptions.length ? (
                <div className="space-y-1.5">
                  <span className="text-xs text-muted-foreground">Ubah status ke</span>
                  <Select key={selKey} onValueChange={(v) => change(v).catch(() => {})} disabled={busy}>
                    <SelectTrigger data-testid={T.orderStatusSelect}><SelectValue placeholder="Pilih status berikutnya" /></SelectTrigger>
                    <SelectContent>
                      {nextOptions.map((s) => <SelectItem key={s} value={s}>{ORDER_STATUS_META[s]?.label || s}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              ) : <p className="text-sm text-muted-foreground">Status final — tidak ada transisi lanjutan.</p>}

              {canCancel ? (
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="outline" className="w-full text-rose-600 border-rose-200" data-testid={T.orderCancel} disabled={busy}>Batalkan Pesanan</Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Batalkan pesanan ini?</AlertDialogTitle>
                      <AlertDialogDescription>Stok akan dikembalikan otomatis. Tindakan ini tidak dapat diurungkan.</AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Tidak</AlertDialogCancel>
                      <AlertDialogAction onClick={() => change('cancelled').catch(() => {})} className="bg-rose-600 hover:bg-rose-700">Ya, Batalkan</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              ) : null}
            </CardContent>
          </Card>

          <Card className="border-border/70">
            <CardHeader><CardTitle className="text-base">Pengiriman</CardTitle></CardHeader>
            <CardContent className="text-sm space-y-1">
              <div className="font-medium">{order.address?.name}</div>
              <div className="text-muted-foreground">{order.address?.phone}</div>
              <div className="text-muted-foreground">{order.address?.street}, {order.address?.city}, {order.address?.province} {order.address?.postal}</div>
              <div className="pt-2 text-xs">Kurir: {order.shipping?.name || order.shipping_id || '—'}</div>
              <div className="text-xs">Bayar: {order.payment?.name || order.payment?.method_id || '—'}</div>
              {order.shipment ? (
                <div className="mt-3 rounded-md border border-border/70 p-3" data-testid="admin-order-shipment">
                  <div className="text-xs text-muted-foreground">Resi · {order.shipment.courier_name}</div>
                  <div className="font-mono text-base font-semibold" data-testid="admin-order-tracking-number">{order.shipment.tracking_number}</div>
                  <div className="mt-2 flex gap-2">
                    <a href={order.shipment.tracking_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs underline" data-testid="admin-order-tracking-link">Lacak <ExternalLink className="h-3 w-3" /></a>
                    {order.status === 'shipped' ? (
                      <button type="button" onClick={() => setShip('edit')} className="inline-flex items-center gap-1 text-xs underline" data-testid="admin-order-edit-resi">Ubah resi <Pencil className="h-3 w-3" /></button>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>
      <ShipDialog open={!!ship} onOpenChange={(o) => !o && setShip(null)} order={order} edit={ship === 'edit'} onSubmit={submitShip} />
    </div>
  );
}
