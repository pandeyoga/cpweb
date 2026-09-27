// components/admin/media/MediaPageView.js — tampilan Media Manager (dipisah dari AdminMediaPage: state/aksi di page).
import React from 'react';
import { FolderInput, FolderTree as FolderTreeIcon, HardDrive, Loader2, RefreshCw, AlertTriangle, ShieldCheck, Trash2, X } from 'lucide-react';
import { Badge } from '../../ui/badge';
import { Button } from '../../ui/button';
import { Card, CardContent } from '../../ui/card';
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from '../../ui/sheet';
import { MetricCard, PageHeader, ACCENT, ACCENT_SOFT } from '../adminUi';
import { MediaToolbar } from './MediaToolbar';
import { AssetDetailsPanel } from './AssetDetailsPanel';
import { Dropzone } from './Dropzone';
import { UploadQueuePanel } from './UploadQueuePanel';
import {
  ConfirmDialog, FolderNameDialog, FromUrlDialog, MoveToFolderDialog,
} from './MediaDialogs';
import { HiddenPicker, ConfirmFolderDialog } from './MediaPageHelpers';
import { adminTestIds as T } from '../../../constants/testIds/admin';
import { formatBytes } from '../../../lib/mediaUrl';

export const MediaPageView = ({
  activeFolder, allSelected, assetsArea, confirm, doBulkDelete, doDeleteAsset,
  doDeleteFolder, doLocalize, doMoveAssets, doReplace, dropOverlay, dropzoneRef,
  flat, focused, folderDialog, folderId, folderNameOf, items,
  kind, localizing, mobileDetails, mobileRail, moveDialog, page,
  pages, qInput, railContent, rangeFrom, rangeTo, recursive,
  refreshAll, saveAsset, saving, selected, setConfirm, setFocused,
  setFolderDialog, setFolderId, setKind, setMobileDetails, setMobileRail, setMoveDialog,
  setPage, setQInput, setRecursive, setSelected, setSort, setUrlDialog,
  setView, sort, stats, submitFolder, submitUrl, toggleAll,
  total, upload, urlDialog, view,
}) => (
  <div data-testid={T.mediaPage}>
    <PageHeader
      title="Media"
      description="Kelola gambar untuk produk, konten, kategori, lokasi toko, dan pembayaran. Semua berkas tersimpan di penyimpanan lokal server."
      testId={T.mediaPageHeader}
      actions={(
        <>
          <Button
            variant="secondary"
            className="gap-2 rounded-lg xl:hidden"
            onClick={() => setMobileRail(true)}
            data-testid={T.mediaOpenRail}
          >
            <FolderTreeIcon className="h-4 w-4" /> Folder
          </Button>
          <Button
            variant="secondary"
            className="gap-2 rounded-lg"
            onClick={refreshAll}
            data-testid={T.mediaRefresh}
          >
            <RefreshCw className="h-4 w-4" /> Muat Ulang
          </Button>
        </>
      )}
    />

    {/* ---------- statistik penyimpanan ---------- */}
    <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
      <MetricCard
        label="Jumlah berkas"
        value={stats ? stats.assets : '—'}
        sub={stats ? `${stats.local_assets} berkas lokal` : ' '}
        testId={T.mediaStatFiles}
        accent
      />
      <MetricCard
        label="Total ukuran"
        value={stats ? formatBytes(stats.bytes) : '—'}
        sub={stats ? `di disk: ${formatBytes(stats.disk_bytes)}` : ' '}
        testId={T.mediaStatSize}
      />
      <MetricCard
        label="Folder"
        value={stats ? stats.folders : '—'}
        sub="bertingkat tanpa batas"
        testId={T.mediaStatFolders}
      />
      <MetricCard
        label="Batas upload"
        value={stats ? `${stats.max_mb} MB` : '—'}
        sub={stats?.mirror ? 'cadangan otomatis aktif' : 'cadangan otomatis nonaktif'}
        testId={T.mediaStatLimit}
      />
    </div>

    {/* ---------- peringatan gambar hotlink (penyebab broken image) ---------- */}
    {stats && stats.hotlinked > 0 ? (
      <div
        className="mb-5 flex flex-col gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between"
        data-testid={T.mediaHotlinkWarning}
      >
        <div className="flex min-w-0 items-start gap-2.5">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" aria-hidden="true" />
          <div className="min-w-0">
            <p className="text-sm font-medium text-amber-900">
              {stats.hotlinked} gambar masih menautkan ke situs luar
            </p>
            <p className="mt-0.5 text-xs leading-relaxed text-amber-800">
              Gambar seperti ini bisa jadi <strong>broken</strong> kapan saja bila situs sumbernya
              mati atau memblokir hotlink. Klik perbaiki untuk mengunduh semuanya ke penyimpanan
              lokal — referensi di produk, kategori, konten, lokasi toko, dan pembayaran otomatis
              diperbarui.
            </p>
          </div>
        </div>
        <Button
          className="shrink-0 gap-2 rounded-lg"
          onClick={() => setConfirm({ kind: 'localize' })}
          disabled={localizing}
          data-testid={T.mediaLocalizeBtn}
        >
          {localizing ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
          {localizing ? 'Memperbaiki…' : 'Perbaiki Sekarang'}
        </Button>
      </div>
    ) : null}

    <div className="grid grid-cols-12 gap-4">
      {/* ---------- rail folder (desktop) ---------- */}
      <aside className="hidden xl:col-span-2 xl:block">
        <div className="sticky top-4 overflow-hidden rounded-2xl border border-border/70 bg-card">
          <div className="flex items-center justify-between border-b border-border/70 px-3 py-2.5">
            <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Folder
            </span>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 rounded-md px-2 text-xs"
              onClick={() => setFolderDialog({ mode: 'create', parentId: folderId || null })}
              data-testid={T.mediaRailNewFolder}
            >
              + Baru
            </Button>
          </div>
          <div className="max-h-[62vh] overflow-y-auto p-2">{railContent}</div>
        </div>
      </aside>

      {/* ---------- kanvas aset ---------- */}
      <main className="col-span-12 min-w-0 xl:col-span-7">
        <Card className="border-border/70">
          <CardContent className="p-4">
            <div className="mb-3 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground" data-testid={T.mediaBreadcrumb}>
              <button
                type="button"
                className="rounded px-1 py-0.5 transition-colors hover:bg-muted hover:text-foreground"
                onClick={() => { setFolderId(''); setPage(1); }}
              >
                Semua Media
              </button>
              {(activeFolder?.path || '').split('/').filter(Boolean).map((seg, i, arr) => (
                <React.Fragment key={`${seg}-${i}`}>
                  <span aria-hidden="true">/</span>
                  <span className={i === arr.length - 1 ? 'font-medium text-foreground' : ''}>{seg}</span>
                </React.Fragment>
              ))}
            </div>

            <MediaToolbar
              query={qInput}
              onQueryChange={setQInput}
              kind={kind}
              onKindChange={(v) => { setKind(v); setPage(1); }}
              sort={sort}
              onSortChange={(v) => { setSort(v); setPage(1); }}
              view={view}
              onViewChange={setView}
              onUpload={() => dropzoneRef.current?.pick?.()}
              onNewFolder={() => setFolderDialog({ mode: 'create', parentId: folderId || null })}
              onFromUrl={() => setUrlDialog(true)}
              recursive={recursive}
              onRecursiveChange={folderId ? (v) => { setRecursive(v); setPage(1); } : null}
              className="mb-4"
            />

            {/* Dropzone tipis selalu terlihat (fallback non-drag). */}
            <Dropzone
              onFiles={upload.enqueue}
              busy={upload.busy}
              compact
              className="mb-4"
              title={folderId ? `Seret berkas ke folder “${activeFolder?.name}”` : 'Seret & lepas gambar di sini'}
            />

            <UploadQueuePanel
              queue={upload.queue}
              onRetry={upload.retry}
              onRemove={upload.remove}
              onClearDone={upload.clearDone}
              className="mb-4"
            />

            {assetsArea}

            {total > 0 ? (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-border/60 pt-3">
                <span className="text-[11px] text-muted-foreground" data-testid={T.mediaPageInfo}>
                  Menampilkan {rangeFrom}–{rangeTo} dari {total} berkas
                </span>
                {pages > 1 ? (
                  <div className="flex gap-1.5">
                    <Button
                      size="sm"
                      variant="secondary"
                      className="h-7 rounded-md px-2 text-xs"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      data-testid={T.mediaPrevPage}
                    >
                      Sebelumnya
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      className="h-7 rounded-md px-2 text-xs"
                      disabled={page >= pages}
                      onClick={() => setPage((p) => Math.min(pages, p + 1))}
                      data-testid={T.mediaNextPage}
                    >
                      Berikutnya
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* ---------- bilah aksi massal ---------- */}
        {selected.length ? (
          <div
            className="sticky bottom-4 z-20 mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border/70 bg-card px-4 py-3 shadow-lg"
            data-testid={T.mediaBulkBar}
          >
            <div className="flex items-center gap-2">
              <Badge variant="outline" style={{ borderColor: ACCENT, color: ACCENT, background: ACCENT_SOFT }}>
                {selected.length} dipilih
              </Badge>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 rounded-md px-2 text-xs"
                onClick={toggleAll}
                data-testid={T.mediaBulkSelectAll}
              >
                {allSelected ? 'Batal pilih semua' : 'Pilih semua di halaman ini'}
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                className="gap-1.5 rounded-lg"
                onClick={() => setMoveDialog({ ids: selected })}
                data-testid={T.mediaBulkMove}
              >
                <FolderInput className="h-3.5 w-3.5" /> Pindahkan
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5 rounded-lg border-rose-200 text-rose-600 hover:bg-rose-50"
                onClick={() => setConfirm({ kind: 'bulk' })}
                data-testid={T.mediaBulkDelete}
              >
                <Trash2 className="h-3.5 w-3.5" /> Hapus
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="gap-1.5"
                onClick={() => setSelected([])}
                data-testid={T.mediaBulkClear}
              >
                <X className="h-3.5 w-3.5" /> Batal
              </Button>
            </div>
          </div>
        ) : null}
      </main>

      {/* ---------- inspektur (desktop xl) ---------- */}
      <aside className="hidden xl:col-span-3 xl:block">
        <div className="sticky top-4 max-h-[calc(100vh-2rem)]">
          <AssetDetailsPanel
            asset={focused}
            folderName={folderNameOf(focused?.folder_id)}
            busy={saving}
            onSave={saveAsset}
            onMove={(a) => setMoveDialog({ ids: [a.id] })}
            onReplace={doReplace}
            onDelete={(a) => setConfirm({ kind: 'asset', payload: a })}
            onClose={() => setFocused(null)}
          />
        </div>
      </aside>
    </div>

    {/* ---------- overlay drag & drop global ---------- */}
    {dropOverlay ? (
      <div
        className="fixed inset-0 z-50 bg-background/75 backdrop-blur-[2px]"
        data-testid={T.mediaDropOverlay}
      >
        <div
          className="mx-auto mt-32 max-w-xl rounded-2xl border-2 border-dashed bg-card p-10 text-center shadow-xl"
          style={{ borderColor: ACCENT }}
        >
          <HardDrive className="mx-auto h-9 w-9" style={{ color: ACCENT }} aria-hidden="true" />
          <p className="mt-3 font-['DM_Serif_Display',serif] text-xl text-foreground">
            Lepaskan untuk mengunggah
          </p>
          <p className="mt-1.5 text-xs text-muted-foreground">
            Berkas akan disimpan di {folderId ? `folder “${activeFolder?.name}”` : 'Semua Media'} ·
            maks {stats?.max_mb || 15}MB per berkas
          </p>
        </div>
      </div>
    ) : null}

    {/* ---------- Sheet: rail folder (mobile/tablet) ---------- */}
    <Sheet open={mobileRail} onOpenChange={setMobileRail}>
      <SheetContent side="left" className="w-[300px] overflow-y-auto p-0">
        <SheetHeader className="border-b border-border/70 px-4 py-3">
          <SheetTitle className="text-base">Folder</SheetTitle>
          <SheetDescription className="text-xs">
            Folder bertingkat untuk merapikan media.
          </SheetDescription>
        </SheetHeader>
        <div className="p-2">
          <Button
            size="sm"
            variant="secondary"
            className="mb-2 w-full rounded-lg"
            onClick={() => { setFolderDialog({ mode: 'create', parentId: folderId || null }); setMobileRail(false); }}
          >
            + Folder Baru
          </Button>
          {railContent}
        </div>
      </SheetContent>
    </Sheet>

    {/* ---------- Sheet: inspektur (mobile/tablet) ---------- */}
    <Sheet
      open={mobileDetails && !!focused}
      onOpenChange={(v) => { setMobileDetails(v); if (!v) setFocused(null); }}
    >
      <SheetContent side="right" className="w-full overflow-y-auto p-0 sm:max-w-md">
        <SheetHeader className="border-b border-border/70 px-4 py-3">
          <SheetTitle className="text-base">Detail Berkas</SheetTitle>
          <SheetDescription className="text-xs">
            Ubah alt text, pindahkan folder, salin URL, atau hapus berkas.
          </SheetDescription>
        </SheetHeader>
        <div className="p-3">
          <AssetDetailsPanel
            asset={focused}
            folderName={folderNameOf(focused?.folder_id)}
            busy={saving}
            onSave={saveAsset}
            onMove={(a) => setMoveDialog({ ids: [a.id] })}
            onReplace={doReplace}
            onDelete={(a) => setConfirm({ kind: 'asset', payload: a })}
            onClose={() => { setMobileDetails(false); setFocused(null); }}
          />
        </div>
      </SheetContent>
    </Sheet>

    {/* ---------- dialog ---------- */}
    <FolderNameDialog
      open={!!folderDialog}
      onOpenChange={(v) => !v && setFolderDialog(null)}
      mode={folderDialog?.mode || 'create'}
      initialName={folderDialog?.node?.name || ''}
      parentPath={folderDialog?.parentId ? folderNameOf(folderDialog.parentId) : ''}
      onSubmit={submitFolder}
      busy={saving}
    />

    <MoveToFolderDialog
      open={!!moveDialog}
      onOpenChange={(v) => !v && setMoveDialog(null)}
      folders={flat}
      count={moveDialog?.ids?.length || 1}
      currentFolderId={folderId || null}
      onSubmit={(target) => doMoveAssets(moveDialog.ids, target)}
      busy={saving}
    />

    <FromUrlDialog
      open={urlDialog}
      onOpenChange={setUrlDialog}
      onSubmit={submitUrl}
      busy={saving}
      folderPath={activeFolder?.name || ''}
    />

    <ConfirmDialog
      open={confirm?.kind === 'asset'}
      onOpenChange={(v) => !v && setConfirm(null)}
      title="Hapus berkas ini?"
      description={`“${confirm?.payload?.filename || ''}” akan dihapus permanen dari penyimpanan lokal. Produk atau konten yang memakainya akan menampilkan placeholder.`}
      confirmLabel="Hapus berkas"
      onConfirm={doDeleteAsset}
      busy={saving}
    />

    <ConfirmDialog
      open={confirm?.kind === 'bulk'}
      onOpenChange={(v) => !v && setConfirm(null)}
      title={`Hapus ${selected.length} berkas?`}
      description="Semua berkas terpilih akan dihapus permanen dari penyimpanan lokal. Tindakan ini tidak bisa dibatalkan."
      confirmLabel="Hapus semua"
      onConfirm={doBulkDelete}
      busy={saving}
    />

    <ConfirmDialog
      open={confirm?.kind === 'localize'}
      onOpenChange={(v) => !v && setConfirm(null)}
      title={`Unduh ${stats?.hotlinked || 0} gambar eksternal ke lokal?`}
      description="Setiap gambar akan diunduh ke penyimpanan lokal server, lalu semua referensinya di produk, kategori, konten situs, lokasi toko, dan metode pembayaran diperbarui otomatis. Proses ini aman dan bisa diulang. Gambar yang sumbernya sudah mati akan dilaporkan sebagai gagal."
      confirmLabel="Unduh & Perbaiki"
      onConfirm={doLocalize}
      busy={localizing}
      testId={T.mediaLocalizeDialog}
      confirmTestId={T.mediaLocalizeConfirm}
    />

    {/* Hapus folder: dua pilihan aman (pindahkan isi) atau cascade. */}
    {confirm?.kind === 'folder' ? (
      <ConfirmFolderDialog
        node={confirm.payload}
        busy={saving}
        onCancel={() => setConfirm(null)}
        onSafe={() => doDeleteFolder(false)}
        onCascade={() => doDeleteFolder(true)}
      />
    ) : null}

    {/* Dropzone tersembunyi untuk tombol Upload di toolbar. */}
    <HiddenPicker ref={dropzoneRef} onFiles={upload.enqueue} />
  </div>
);
