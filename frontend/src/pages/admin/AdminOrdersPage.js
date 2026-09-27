// pages/admin/AdminOrdersPage.js — daftar pesanan + filter status (BR-6).
import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { listOrdersPage } from '../../services/admin';
import { Input } from '../../components/ui/input';
import { formatIDR } from '../../lib/format';
import {
  PageHeader, TableSkeleton, EmptyState, StatusBadge, formatDateTime, ORDER_STATUSES, ORDER_STATUS_META,
} from '../../components/admin/adminUi';
import { adminTestIds as T } from '../../constants/testIds/admin';
import { Card, CardContent } from '../../components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../../components/ui/table';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../../components/ui/select';
import { Button } from '../../components/ui/button';

export default function AdminOrdersPage() {
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('all');
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [total, setTotal] = useState(0);
  const [more, setMore] = useState(false);
  const PAGE = 50;

  useEffect(() => { const t = setTimeout(() => setQuery(q.trim()), 350); return () => clearTimeout(t); }, [q]);
  const fetchPage = useCallback((skip) => listOrdersPage({ status: status === 'all' ? '' : status, q: query, skip, limit: PAGE }), [status, query]);
  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await fetchPage(0); setRows(r.items); setTotal(r.total); }
    catch (e) { toast.error('Gagal memuat pesanan.'); }
    finally { setLoading(false); }
  }, [fetchPage]);
  useEffect(() => { load(); }, [load]);
  const loadMore = async () => {
    setMore(true);
    try { const r = await fetchPage(rows.length); setRows((prev) => [...prev, ...r.items]); setTotal(r.total); }
    catch (e) { toast.error('Gagal memuat pesanan.'); }
    finally { setMore(false); }
  };

  return (
    <div>
      <PageHeader title="Pesanan" description="Proses & pantau pesanan pelanggan." />
      <Card className="border-border/70"><CardContent className="p-4">
        <div className="flex flex-col sm:flex-row gap-2 sm:items-center justify-between mb-4">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari kode, email, nama, atau telepon" className="sm:max-w-sm" data-testid="admin-orders-search" />
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-full sm:w-52" data-testid={T.ordersStatusSelect}><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Semua Status</SelectItem>
              {ORDER_STATUSES.map((s) => <SelectItem key={s} value={s}>{ORDER_STATUS_META[s].label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        {loading ? <TableSkeleton rows={6} cols={5} /> : (
          rows.length === 0 ? <EmptyState title="Belum ada pesanan" /> : (
            <div className="overflow-x-auto">
              <Table data-testid={T.ordersTable}>
                <TableHeader><TableRow>
                  <TableHead>Kode</TableHead><TableHead>Pelanggan</TableHead><TableHead>Tanggal</TableHead>
                  <TableHead>Status</TableHead><TableHead className="text-right">Total</TableHead><TableHead className="w-24" />
                </TableRow></TableHeader>
                <TableBody>
                  {rows.map((o) => (
                    <TableRow key={o.code}>
                      <TableCell className="font-[\'Azeret_Mono\',monospace] text-xs">{o.code}</TableCell>
                      <TableCell className="text-sm">
                        <div className="truncate max-w-[180px]">{o.address?.name || o.customer?.name || '—'}</div>
                        <div className="text-[11px] text-muted-foreground truncate max-w-[180px]">{o.customer_email || o.address?.phone || ''}</div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{formatDateTime(o.created_at)}</TableCell>
                      <TableCell><StatusBadge status={o.status} /></TableCell>
                      <TableCell className="text-right font-[\'Azeret_Mono\',monospace] text-sm">{formatIDR(o.total || 0)}</TableCell>
                      <TableCell className="text-right">
                        <Button variant="secondary" size="sm" onClick={() => navigate(`/admin/pesanan/${o.code}`)}>Proses</Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )
        )}
        {!loading && rows.length > 0 ? (
          <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground" data-testid="admin-orders-count">
            <span>Menampilkan {rows.length} dari {total} pesanan</span>
            {rows.length < total ? (
              <Button variant="outline" size="sm" onClick={loadMore} disabled={more} data-testid="admin-orders-load-more">
                {more ? 'Memuat…' : 'Muat lebih banyak'}
              </Button>
            ) : null}
          </div>
        ) : null}
      </CardContent></Card>
    </div>
  );
}
