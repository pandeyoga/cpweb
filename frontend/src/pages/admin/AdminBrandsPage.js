// pages/admin/AdminBrandsPage.js — profil brand untuk section "Jelajahi Koleksi" & filter Toko:
// logo (SVG/PNG), foto kartu, deskripsi, urutan manual, sembunyikan. Daftar brand = field `brand` produk.
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Pencil, Search, Store } from 'lucide-react';
import { PageHeader, TableSkeleton, EmptyState } from '../../components/admin/adminUi';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge } from '../../components/ui/badge';
import { Card, CardContent } from '../../components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../../components/ui/table';
import { SmartImage } from '../../components/shared/SmartImage';
import { listBrandsAdmin } from '../../services/admin';
import { BrandDialog } from '../../components/admin/brands/BrandDialog';

const PAGE = 50;

export default function AdminBrandsPage() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [limit, setLimit] = useState(PAGE);
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { setRows(await listBrandsAdmin()); } catch (e) { toast.error('Gagal memuat brand.'); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const list = useMemo(() => rows.filter((b) => b.name.toLowerCase().includes(q.trim().toLowerCase())), [rows, q]);

  return (
    <div>
      <PageHeader title="Brand" description="Logo, foto kartu & urutan brand di section Jelajahi Koleksi (beranda) dan filter Toko. Daftar brand diambil otomatis dari produk." />
      <Card className="border-border/70"><CardContent className="p-4 space-y-4">
        <div className="relative max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => { setQ(e.target.value); setLimit(PAGE); }} placeholder={`Cari dari ${rows.length} brand…`} className="pl-9" data-testid="admin-brands-search" />
        </div>
        {loading ? <TableSkeleton rows={6} cols={5} /> : list.length === 0 ? <EmptyState title="Tidak ada brand" /> : (
          <Table data-testid="admin-brands-table">
            <TableHeader><TableRow>
              <TableHead className="w-16">Logo</TableHead><TableHead className="w-20">Foto</TableHead><TableHead>Brand</TableHead>
              <TableHead className="w-28">Produk aktif</TableHead><TableHead className="w-20">Urutan</TableHead><TableHead>Status</TableHead><TableHead className="w-16" />
            </TableRow></TableHeader>
            <TableBody>
              {list.slice(0, limit).map((b) => (
                <TableRow key={b.name} data-testid="admin-brand-row">
                  <TableCell>
                    <span className="h-10 w-10 rounded-lg border bg-white grid place-items-center overflow-hidden">
                      {b.logo ? <SmartImage src={b.logo} alt="" className="h-full w-full object-contain p-1" /> : <Store className="h-4 w-4 text-muted-foreground" />}
                    </span>
                  </TableCell>
                  <TableCell>
                    {b.image ? <SmartImage src={b.image} alt="" className="h-10 w-14 rounded-md object-cover" /> : <span className="text-xs text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell className="font-medium">{b.name}</TableCell>
                  <TableCell className="text-sm">{b.active_count} / {b.count}</TableCell>
                  <TableCell className="text-sm">{b.order || '—'}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={b.hidden ? 'bg-zinc-100 text-zinc-600' : 'bg-emerald-100 text-emerald-800 border-emerald-200'}>
                      {b.hidden ? 'Disembunyikan' : 'Tampil'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon" onClick={() => setEditing(b)} aria-label="Edit" data-testid="admin-brand-edit"><Pencil className="h-4 w-4" /></Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {list.length > limit ? (
          <Button variant="secondary" onClick={() => setLimit((n) => n + PAGE)} data-testid="admin-brands-more">Tampilkan lebih banyak ({list.length - limit})</Button>
        ) : null}
      </CardContent></Card>
      <BrandDialog brand={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
    </div>
  );
}
