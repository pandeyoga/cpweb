// components/admin/media/MediaPageHelpers.js — picker tersembunyi & dialog hapus folder (Media Manager).
import React, { useRef } from 'react';
import { Copy, FolderInput, Loader2, Trash2 } from 'lucide-react';
import { Button } from '../../ui/button';
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from '../../ui/sheet';
import { ACCENT } from '../adminUi';
import { adminTestIds as T } from '../../../constants/testIds/admin';

// Tombol "Upload" pada toolbar memicu input berkas tersembunyi ini.
export const HiddenPicker = React.forwardRef(({ onFiles }, ref) => {
  const inputRef = useRef(null);
  React.useImperativeHandle(ref, () => ({ pick: () => inputRef.current?.click() }));
  return (
    <input
      ref={inputRef}
      type="file"
      multiple
      accept="image/*"
      className="hidden"
      onChange={(e) => {
        if (e.target.files?.length) onFiles(e.target.files);
        e.target.value = '';
      }}
      data-testid={T.mediaToolbarFileInput}
    />
  );
});

export const ConfirmFolderDialog = ({ node, onCancel, onSafe, onCascade, busy }) => (
  <Sheet open onOpenChange={(v) => !v && onCancel()}>
    <SheetContent side="right" className="w-full sm:max-w-md">
      <SheetHeader>
        <SheetTitle className="text-base">Hapus folder “{node?.name}”?</SheetTitle>
        <SheetDescription className="text-xs">
          Pilih cara menghapus. Opsi aman TIDAK menghapus berkas apa pun.
        </SheetDescription>
      </SheetHeader>
      <div className="mt-5 space-y-3" data-testid={T.mediaFolderDeleteDialog}>
        <button
          type="button"
          onClick={onSafe}
          disabled={busy}
          className="w-full rounded-xl border border-border/70 bg-card p-4 text-left transition-colors hover:bg-muted/60"
          data-testid={T.mediaFolderDeleteSafe}
        >
          <div className="flex items-center gap-2 text-sm font-medium text-foreground">
            <FolderInput className="h-4 w-4" style={{ color: ACCENT }} /> Pindahkan isi ke folder induk
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Disarankan. Folder dihapus, tetapi semua berkas & subfolder di dalamnya dipindahkan
            ke induknya — tidak ada gambar yang hilang.
          </p>
        </button>
        <button
          type="button"
          onClick={onCascade}
          disabled={busy}
          className="w-full rounded-xl border border-rose-200 bg-rose-50/60 p-4 text-left transition-colors hover:bg-rose-50"
          data-testid={T.mediaFolderDeleteCascade}
        >
          <div className="flex items-center gap-2 text-sm font-medium text-rose-700">
            <Trash2 className="h-4 w-4" /> Hapus folder & semua isinya
          </div>
          <p className="mt-1 text-xs leading-relaxed text-rose-700/80">
            Permanen. Seluruh berkas dan subfolder di dalamnya akan dihapus dari penyimpanan.
          </p>
        </button>
        <Button variant="secondary" className="w-full rounded-lg" onClick={onCancel}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Batal
        </Button>
        <p className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <Copy className="h-3 w-3" /> Tip: gunakan “Pindahkan” pada berkas jika hanya ingin merapikan.
        </p>
      </div>
    </SheetContent>
  </Sheet>
);
