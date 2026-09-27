// components/admin/ContactMessages.js — pesan dari formulir Kontak (tersimpan di server).
import React, { useEffect, useState } from 'react';
import { listContactMessages } from '../../services/forms';
import { EmptyState, TableSkeleton, formatDateTime } from './adminUi';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';

export const ContactMessages = () => {
  const [rows, setRows] = useState(null);
  useEffect(() => { listContactMessages().then(setRows).catch(() => setRows([])); }, []);
  return (
    <Card className="border-border/70 mt-6" data-testid="admin-contact-messages">
      <CardHeader className="pb-2"><CardTitle className="text-base">Pesan Formulir Kontak</CardTitle></CardHeader>
      <CardContent>
        {rows === null ? <TableSkeleton rows={3} cols={3} /> : rows.length === 0 ? (
          <EmptyState title="Belum ada pesan" />
        ) : (
          <ul className="divide-y">
            {rows.map((m) => (
              <li key={m.id} className="py-3 text-sm" data-testid="admin-contact-message-row">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-medium">{m.name}</span>
                  <a href={`mailto:${m.email}`} className="text-muted-foreground underline-offset-2 hover:underline">{m.email}</a>
                  <span className="ml-auto text-xs text-muted-foreground">{formatDateTime(m.created_at)}</span>
                </div>
                {m.subject ? <div className="text-xs font-semibold mt-1">{m.subject}</div> : null}
                <p className="mt-1 whitespace-pre-wrap text-muted-foreground break-words">{m.message}</p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
};
