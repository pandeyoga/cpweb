// pages/admin/AdminMediaPage.js — Media Manager (E20).
//
// Pusat kelola berkas gambar untuk produk, konten, kategori, lokasi toko, dan
// pengaturan pembayaran. Semua berkas disimpan di penyimpanan LOKAL server.
//
// Layout master-detail 3 kolom (rail folder | kanvas aset | inspektur detail).
// Di bawah xl inspektur memakai <Sheet>; di mobile rail folder juga <Sheet>.
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../../components/ui/button';
import { EmptyState } from '../../components/admin/adminUi';
import { FolderTree, flattenTree } from '../../components/admin/media/FolderTree';
import { AssetGrid, AssetList } from '../../components/admin/media/AssetGrid';
import { Dropzone } from '../../components/admin/media/Dropzone';
import { useMediaUpload } from '../../components/admin/media/useMediaUpload';
import { resolveMediaUrl } from '../../lib/mediaUrl';
import { bulkDeleteAssets, bulkMoveAssets, createFolder, deleteAsset, deleteFolder, getFolderTree, getMediaStats, ingestUrl, listAssets, localizeExternalMedia, mediaErrorMessage, moveAsset, moveFolder, renameFolder, replaceAsset, updateAsset } from '../../services/media';
import { MediaPageView } from '../../components/admin/media/MediaPageView';

const PAGE_SIZE = 40;

export default function AdminMediaPage() {
  // ---------- state data ----------
  const [tree, setTree] = useState([]);
  const [root, setRoot] = useState(null);
  const [folderId, setFolderId] = useState('');
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // ---------- state UI ----------
  const [qInput, setQInput] = useState('');
  const [q, setQ] = useState('');
  const [kind, setKind] = useState('all');
  const [sort, setSort] = useState('newest');
  const [view, setView] = useState('grid');
  const [recursive, setRecursive] = useState(true);
  const [selected, setSelected] = useState([]);
  const [focused, setFocused] = useState(null);
  const [mobileRail, setMobileRail] = useState(false);
  const [mobileDetails, setMobileDetails] = useState(false);

  // ---------- dialog ----------
  const [folderDialog, setFolderDialog] = useState(null); // {mode, parentId, node}
  const [moveDialog, setMoveDialog] = useState(null);     // {ids} | {folder}
  const [urlDialog, setUrlDialog] = useState(false);
  const [confirm, setConfirm] = useState(null);           // {kind, payload}
  const [dropOverlay, setDropOverlay] = useState(false);
  const dragDepth = useRef(0);
  const dropzoneRef = useRef(null);

  const flat = useMemo(() => flattenTree(tree), [tree]);
  const activeFolder = folderId ? flat.find((f) => f.id === folderId) : null;
  const folderNameOf = (id) => (id ? (flat.find((f) => f.id === id)?.name || '—') : 'Semua Media');

  // ---------- loaders ----------
  const loadTree = useCallback(async () => {
    try {
      const t = await getFolderTree();
      setTree(t?.tree || []);
      setRoot(t?.root || null);
    } catch (e) {
      toast.error(mediaErrorMessage(e, 'Gagal memuat daftar folder.'));
    }
  }, []);

  const loadStats = useCallback(async () => {
    try { setStats(await getMediaStats()); } catch (e) { /* opsional */ }
  }, []);

  const loadAssets = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listAssets({
        folderId: folderId || '',
        q,
        kind: kind === 'all' ? '' : kind,
        sort,
        page,
        limit: PAGE_SIZE,
        recursive: !!folderId && recursive,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (e) {
      toast.error(mediaErrorMessage(e, 'Gagal memuat pustaka media.'));
      setItems([]);
      setTotal(0);
    } finally { setLoading(false); }
  }, [folderId, q, kind, sort, page, recursive]);

  useEffect(() => { loadTree(); loadStats(); }, [loadTree, loadStats]);
  useEffect(() => { loadAssets(); }, [loadAssets]);
  useEffect(() => {
    const t = setTimeout(() => { setQ(qInput); setPage(1); }, 320);
    return () => clearTimeout(t);
  }, [qInput]);

  const refreshAll = useCallback(async () => {
    await Promise.all([loadAssets(), loadTree(), loadStats()]);
  }, [loadAssets, loadTree, loadStats]);

  // ---------- upload ----------
  const onUploaded = useCallback((assets) => {
    toast.success(`${assets.length} berkas berhasil diunggah.`);
    refreshAll();
    if (assets.length === 1) setFocused(assets[0]);
  }, [refreshAll]);
  const upload = useMediaUpload({ folderId: folderId || null, onUploaded });

  // Overlay drag & drop pada seluruh kanvas.
  useEffect(() => {
    const hasFiles = (e) => Array.from(e.dataTransfer?.types || []).includes('Files');
    const onEnter = (e) => {
      if (!hasFiles(e)) return;
      dragDepth.current += 1;
      setDropOverlay(true);
    };
    const onLeave = () => {
      dragDepth.current = Math.max(0, dragDepth.current - 1);
      if (dragDepth.current === 0) setDropOverlay(false);
    };
    const onOver = (e) => { if (hasFiles(e)) e.preventDefault(); };
    const onDrop = (e) => {
      dragDepth.current = 0;
      setDropOverlay(false);
      if (!hasFiles(e)) return;
      e.preventDefault();
      if (e.dataTransfer.files?.length) upload.enqueue(e.dataTransfer.files);
    };
    window.addEventListener('dragenter', onEnter);
    window.addEventListener('dragleave', onLeave);
    window.addEventListener('dragover', onOver);
    window.addEventListener('drop', onDrop);
    return () => {
      window.removeEventListener('dragenter', onEnter);
      window.removeEventListener('dragleave', onLeave);
      window.removeEventListener('dragover', onOver);
      window.removeEventListener('drop', onDrop);
    };
  }, [upload]);

  // ---------- aksi folder ----------
  const submitFolder = async (name) => {
    setSaving(true);
    try {
      if (folderDialog?.mode === 'rename') {
        await renameFolder(folderDialog.node.id, name);
        toast.success('Nama folder diperbarui.');
      } else {
        const f = await createFolder(name, folderDialog?.parentId || null);
        toast.success(`Folder “${f.name}” dibuat.`);
        setFolderId(f.id);
      }
      setFolderDialog(null);
      await refreshAll();
    } catch (e) {
      toast.error(mediaErrorMessage(e, 'Gagal menyimpan folder.'));
    } finally { setSaving(false); }
  };

  const doDeleteFolder = async (cascade) => {
    const node = confirm?.payload;
    setSaving(true);
    try {
      const res = await deleteFolder(node.id, cascade);
      toast.success(cascade
        ? 'Folder & seluruh isinya dihapus.'
        : `Folder dihapus. ${res.moved_assets || 0} berkas dipindahkan ke folder induk.`);
      if (folderId === node.id) setFolderId('');
      setConfirm(null);
      await refreshAll();
    } catch (e) {
      toast.error(mediaErrorMessage(e, 'Gagal menghapus folder.'));
    } finally { setSaving(false); }
  };

  const doMoveFolder = async (id, parentId) => {
    try {
      await moveFolder(id, parentId);
      toast.success('Folder dipindahkan.');
      await refreshAll();
    } catch (e) {
      toast.error(mediaErrorMessage(e, 'Gagal memindahkan folder.'));
    }
  };

  // ---------- aksi aset ----------
  const toggleSelect = (id) => setSelected((s) => (
    s.includes(id) ? s.filter((x) => x !== id) : [...s, id]
  ));
  const allSelected = items.length > 0 && items.every((i) => selected.includes(i.id));
  const toggleAll = () => setSelected(allSelected ? [] : items.map((i) => i.id));

  const openAsset = (asset) => {
    setFocused(asset);
    if (window.innerWidth < 1280) setMobileDetails(true);
  };

  const copyUrl = async (asset) => {
    const abs = resolveMediaUrl(asset.url);
    try {
      await navigator.clipboard.writeText(abs);
      toast.success('Tautan disalin.');
    } catch (e) {
      toast.error('Tidak bisa menyalin otomatis. Buka detail berkas untuk menyalin manual.');
    }
  };

  const saveAsset = async (patch) => {
    if (!focused) return;
    setSaving(true);
    try {
      const updated = await updateAsset(focused.id, patch);
      setFocused(updated);
      setItems((arr) => arr.map((a) => (a.id === updated.id ? updated : a)));
      toast.success('Perubahan disimpan.');
    } catch (e) {
      toast.error(mediaErrorMessage(e, 'Gagal menyimpan perubahan.'));
    } finally { setSaving(false); }
  };

  const doReplace = async (file) => {
    if (!focused) return;
    try {
      const updated = await replaceAsset(focused.id, file);
      setFocused(updated);
      toast.success('Berkas diganti. URL tetap sama.');
      await loadAssets();
    } catch (e) {
      toast.error(mediaErrorMessage(e, 'Gagal mengganti berkas.'));
    }
  };

  const doDeleteAsset = async () => {
    const asset = confirm?.payload;
    setSaving(true);
    try {
      await deleteAsset(asset.id);
      toast.success('Berkas dihapus.');
      if (focused?.id === asset.id) { setFocused(null); setMobileDetails(false); }
      setSelected((s) => s.filter((x) => x !== asset.id));
      setConfirm(null);
      await refreshAll();
    } catch (e) {
      toast.error(mediaErrorMessage(e, 'Gagal menghapus berkas.'));
    } finally { setSaving(false); }
  };

  const doBulkDelete = async () => {
    setSaving(true);
    try {
      const res = await bulkDeleteAssets(selected);
      toast.success(`${res.count || 0} berkas dihapus.`);
      setSelected([]);
      setFocused(null);
      setConfirm(null);
      await refreshAll();
    } catch (e) {
      toast.error(mediaErrorMessage(e, 'Gagal menghapus berkas terpilih.'));
    } finally { setSaving(false); }
  };

  const doMoveAssets = async (ids, targetFolderId) => {
    try {
      if (ids.length === 1) await moveAsset(ids[0], targetFolderId);
      else await bulkMoveAssets(ids, targetFolderId);
      toast.success(`${ids.length} berkas dipindahkan ke ${folderNameOf(targetFolderId)}.`);
      setMoveDialog(null);
      setSelected([]);
      await refreshAll();
    } catch (e) {
      toast.error(mediaErrorMessage(e, 'Gagal memindahkan berkas.'));
    }
  };

  const submitUrl = async (url, alt) => {
    setSaving(true);
    try {
      const asset = await ingestUrl(url, { folderId: folderId || null, alt });
      toast.success('Gambar diunduh & disimpan di penyimpanan lokal.');
      setUrlDialog(false);
      setFocused(asset);
      await refreshAll();
    } catch (e) {
      toast.error(mediaErrorMessage(e, 'Gagal mengunduh gambar dari URL.'));
    } finally { setSaving(false); }
  };

  // Perbaiki gambar yang masih menautkan ke situs luar: unduh ke lokal lalu
  // perbarui semua referensinya (produk, kategori, CMS, toko, pembayaran).
  const [localizing, setLocalizing] = useState(false);
  const doLocalize = async () => {
    setLocalizing(true);
    setConfirm(null);
    try {
      const res = await localizeExternalMedia();
      if (res.converted) {
        toast.success(
          `${res.converted} gambar eksternal berhasil disimpan lokal · ${res.refs_updated} referensi diperbarui.`,
        );
      } else {
        toast.info('Tidak ada gambar eksternal yang perlu diperbaiki.');
      }
      if (res.failed?.length) {
        toast.error(`${res.failed.length} gambar gagal diunduh (sumber tidak dapat diakses).`);
      }
      await refreshAll();
    } catch (e) {
      toast.error(mediaErrorMessage(e, 'Gagal memperbaiki gambar eksternal.'));
    } finally { setLocalizing(false); }
  };

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rangeFrom = total ? (page - 1) * PAGE_SIZE + 1 : 0;
  const rangeTo = Math.min(total, page * PAGE_SIZE);

  // ---------- render ----------
  const railContent = (
    <FolderTree
      tree={tree}
      root={root}
      activeId={folderId}
      onSelect={(id) => { setFolderId(id); setPage(1); setSelected([]); setMobileRail(false); }}
      onCreateChild={(parentId) => setFolderDialog({ mode: 'create', parentId })}
      onRename={(node) => setFolderDialog({ mode: 'rename', node })}
      onDelete={(node) => setConfirm({ kind: 'folder', payload: node })}
      onMoveAssets={doMoveAssets}
      onMoveFolder={doMoveFolder}
    />
  );

  const assetsArea = (
    <>
      {!loading && !items.length ? (
        <div className="space-y-4">
          <EmptyState
            title={q ? 'Tidak ada hasil' : folderId ? 'Folder ini kosong' : 'Belum ada media'}
            hint={q
              ? 'Coba kata kunci lain atau ubah filter tipe.'
              : 'Seret berkas ke halaman ini, klik Upload, atau tambahkan dari URL. Semua gambar disimpan di penyimpanan lokal server.'}
            action={q ? (
              <Button variant="secondary" className="rounded-lg" onClick={() => setQInput('')}>
                Bersihkan pencarian
              </Button>
            ) : null}
          />
          {!q ? (
            <Dropzone onFiles={upload.enqueue} busy={upload.busy} />
          ) : null}
        </div>
      ) : view === 'grid' ? (
        <AssetGrid
          items={items}
          loading={loading}
          selectedIds={selected}
          focusedId={focused?.id}
          onToggleSelect={toggleSelect}
          onOpen={openAsset}
          onDetails={openAsset}
          onCopy={copyUrl}
          onMove={(a) => setMoveDialog({ ids: [a.id] })}
          onDelete={(a) => setConfirm({ kind: 'asset', payload: a })}
        />
      ) : (
        <AssetList
          items={items}
          loading={loading}
          selectedIds={selected}
          focusedId={focused?.id}
          onToggleSelect={toggleSelect}
          onOpen={openAsset}
          onDetails={openAsset}
          onCopy={copyUrl}
          onMove={(a) => setMoveDialog({ ids: [a.id] })}
          onDelete={(a) => setConfirm({ kind: 'asset', payload: a })}
          allSelected={allSelected}
          onToggleAll={toggleAll}
        />
      )}
    </>
  );

  return (
    <MediaPageView
      activeFolder={activeFolder}
      allSelected={allSelected}
      assetsArea={assetsArea}
      confirm={confirm}
      doBulkDelete={doBulkDelete}
      doDeleteAsset={doDeleteAsset}
      doDeleteFolder={doDeleteFolder}
      doLocalize={doLocalize}
      doMoveAssets={doMoveAssets}
      doReplace={doReplace}
      dropOverlay={dropOverlay}
      dropzoneRef={dropzoneRef}
      flat={flat}
      focused={focused}
      folderDialog={folderDialog}
      folderId={folderId}
      folderNameOf={folderNameOf}
      items={items}
      kind={kind}
      localizing={localizing}
      mobileDetails={mobileDetails}
      mobileRail={mobileRail}
      moveDialog={moveDialog}
      page={page}
      pages={pages}
      qInput={qInput}
      railContent={railContent}
      rangeFrom={rangeFrom}
      rangeTo={rangeTo}
      recursive={recursive}
      refreshAll={refreshAll}
      saveAsset={saveAsset}
      saving={saving}
      selected={selected}
      setConfirm={setConfirm}
      setFocused={setFocused}
      setFolderDialog={setFolderDialog}
      setFolderId={setFolderId}
      setKind={setKind}
      setMobileDetails={setMobileDetails}
      setMobileRail={setMobileRail}
      setMoveDialog={setMoveDialog}
      setPage={setPage}
      setQInput={setQInput}
      setRecursive={setRecursive}
      setSelected={setSelected}
      setSort={setSort}
      setUrlDialog={setUrlDialog}
      setView={setView}
      sort={sort}
      stats={stats}
      submitFolder={submitFolder}
      submitUrl={submitUrl}
      toggleAll={toggleAll}
      total={total}
      upload={upload}
      urlDialog={urlDialog}
      view={view}
    />
  );
}
