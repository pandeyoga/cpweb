// components/admin/CmsHistoryDrawer.js — riwayat revisi Konten Situs: pratinjau (ke draft) & pulihkan persis.
import React, { useState } from 'react';
import { History, RotateCcw, X, Loader2, Eye, User } from 'lucide-react';
import { Button } from '../ui/button';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '../ui/alert-dialog';

const fmt = (iso) => new Date(iso).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' });
const noteLabel = (n) => (n === 'revert:default' ? 'sebelum pemulihan ke default'
  : String(n || '').startsWith('revert:') ? 'sebelum pemulihan revisi' : 'sebelum disunting');

const RevisionCard = ({ rev, no, onPreview, onRestore }) => {
  const changed = rev.changed_fields || [];
  return (
    <div className="border border-border/70 rounded-lg p-3 space-y-2 hover:bg-muted/40 transition-colors" data-testid={`cms-revision-${rev.id}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-medium">Revisi #{no}</div>
        <div className="text-[10px] cp-mono text-muted-foreground">{fmt(rev.created_at)}</div>
      </div>
      <div className="text-[11px] text-muted-foreground flex items-center gap-1.5">
        <User className="h-3 w-3" /> {rev.created_by_name || 'Admin'} · {noteLabel(rev.note)}
      </div>
      <div className="flex flex-wrap gap-1" data-testid={`cms-revision-diff-${rev.id}`}>
        {changed.length === 0 ? (
          <span className="text-[11px] text-muted-foreground">Sama dengan versi aktif</span>
        ) : (
          <>
            <span className="text-[11px] text-muted-foreground mr-1">{changed.length} field berbeda:</span>
            {changed.slice(0, 5).map((f) => <span key={f} className="text-[10px] rounded bg-muted px-1.5 py-0.5">{f}</span>)}
            {changed.length > 5 ? <span className="text-[10px] text-muted-foreground">+{changed.length - 5}</span> : null}
          </>
        )}
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" className="gap-1.5 text-xs" onClick={() => onPreview(rev)} data-testid={`cms-preview-${rev.id}`}>
          <Eye className="h-3 w-3" /> Pratinjau
        </Button>
        <Button variant="outline" size="sm" className="gap-1.5 text-xs" disabled={changed.length === 0}
          onClick={() => onRestore({ revision_id: rev.id }, `revisi #${no} (${fmt(rev.created_at)})`)} data-testid={`cms-revert-${rev.id}`}>
          <RotateCcw className="h-3 w-3" /> Pulihkan
        </Button>
      </div>
    </div>
  );
};

export const CmsHistoryDrawer = ({ sectionLabel, revisions, loading, onClose, onPreview, onRestore }) => {
  const [confirm, setConfirm] = useState(null); // {payload, label}
  const ask = (payload, label) => setConfirm({ payload, label });
  return (
    <div className="fixed inset-0 z-50 flex" data-testid="cms-history-drawer">
      <div className="flex-1 bg-black/40" onClick={onClose} />
      <div className="w-full max-w-md bg-background border-l border-border shadow-2xl flex flex-col">
        <div className="p-4 border-b border-border/70 flex items-center justify-between">
          <div>
            <div className="font-semibold flex items-center gap-2"><History className="h-4 w-4" /> Riwayat Perubahan</div>
            <div className="text-xs text-muted-foreground">{sectionLabel} · maksimal 20 revisi terakhir</div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} data-testid="cms-history-close"><X className="h-4 w-4" /></Button>
        </div>
        <div className="p-3 border-b border-border/70">
          <Button variant="outline" size="sm" className="w-full gap-2" onClick={() => ask({ to_default: true }, 'default pabrik')} data-testid="cms-revert-default">
            <RotateCcw className="h-3.5 w-3.5" /> Kembalikan ke Default Pabrik
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {loading ? (
            <div className="py-8 grid place-items-center text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>
          ) : revisions.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-8">Belum ada revisi tersimpan.</div>
          ) : revisions.map((rev, idx) => (
            <RevisionCard key={rev.id} rev={rev} no={revisions.length - idx} onPreview={onPreview} onRestore={ask} />
          ))}
        </div>
      </div>
      <AlertDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <AlertDialogContent data-testid="cms-restore-confirm">
          <AlertDialogHeader>
            <AlertDialogTitle>Pulihkan ke {confirm?.label}?</AlertDialogTitle>
            <AlertDialogDescription>
              Isi bagian ini akan diganti persis seperti versi tersebut — field yang ditambahkan setelahnya ikut dihapus.
              Versi yang aktif sekarang tetap tersimpan di riwayat, jadi bisa dikembalikan lagi.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="cms-restore-cancel">Batal</AlertDialogCancel>
            <AlertDialogAction data-testid="cms-restore-confirm-button" onClick={() => { onRestore(confirm.payload, confirm.label); setConfirm(null); }}>
              Pulihkan
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
