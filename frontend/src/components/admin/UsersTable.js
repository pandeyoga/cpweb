// components/admin/UsersTable.js — daftar semua akun (pelanggan & admin), read-only.
import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { listUsers } from '../../services/admin';
import { EmptyState, TableSkeleton, formatDateTime } from './adminUi';
import { Badge } from '../ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';

export const UsersTable = () => {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    listUsers().then((r) => setRows(r || [])).catch(() => { setRows([]); toast.error('Gagal memuat pengguna.'); });
  }, []);
  if (rows === null) return <TableSkeleton rows={5} cols={4} />;
  if (rows.length === 0) return <EmptyState title="Belum ada pengguna" />;
  return (
    <div className="overflow-x-auto">
      <Table data-testid="admin-users-table">
        <TableHeader><TableRow><TableHead>Nama</TableHead><TableHead>Email</TableHead><TableHead>Peran</TableHead><TableHead>Bergabung</TableHead></TableRow></TableHeader>
        <TableBody>
          {rows.map((u) => (
            <TableRow key={u.id}>
              <TableCell className="font-medium truncate max-w-[240px]" title={u.name || ''}>{u.name || '—'}</TableCell>
              <TableCell className="text-sm text-muted-foreground truncate max-w-[260px]" title={u.email}>{u.email}</TableCell>
              <TableCell><Badge variant="outline" className={u.role === 'admin' ? 'bg-amber-100 text-amber-800 border-amber-200' : 'bg-zinc-100 text-zinc-700 border-zinc-200'}>{u.role === 'admin' ? 'Admin' : 'Pelanggan'}</Badge></TableCell>
              <TableCell className="text-xs text-muted-foreground">{formatDateTime(u.created_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
};
