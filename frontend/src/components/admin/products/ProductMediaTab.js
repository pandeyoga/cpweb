// components/admin/products/ProductMediaTab.js — tab Media editor produk (galeri, unggah, URL, picker).
import React from 'react';
import { Trash2, Star, ImagePlus, Upload, Loader2, ChevronLeft, ChevronRight, Link2 } from 'lucide-react';
import { MediaPickerDialog } from '../media/MediaPickerDialog';
import { SmartImage } from '../../shared/SmartImage';
import { CHECKER_STYLE, isLocalMedia } from '../../../lib/mediaUrl';
import { MEDIA_ACCEPT } from '../../../services/media';
import { adminTestIds as T } from '../../../constants/testIds/admin';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';

export const ProductMediaTab = ({
  form, set, mediaUrl, setMediaUrl, pickerOpen, setPickerOpen, mediaBusy, mediaFileRef,
  uploadProductImages, addFromUrl, addImages, moveImage, setPrimary, rmImage,
}) => (
  <>
      <div className="rounded-xl border border-border/70 bg-muted/40 px-3 py-2.5 text-[11px] leading-relaxed text-muted-foreground">
        Gambar produk diambil dari <strong className="text-foreground">Media Manager</strong> dan
        disimpan di penyimpanan lokal server. Gambar pertama menjadi <strong className="text-foreground">gambar utama</strong> di
        katalog. Seret kartu atau pakai tombol panah untuk mengurutkan.
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          onClick={() => setPickerOpen(true)}
          className="gap-2 rounded-lg"
          data-testid={T.productMediaPick}
        >
          <ImagePlus className="h-4 w-4" /> Pilih dari Media Manager
        </Button>
        <input
          ref={mediaFileRef}
          type="file"
          multiple
          accept={MEDIA_ACCEPT}
          className="hidden"
          onChange={(e) => uploadProductImages(e.target.files)}
          data-testid={T.productMediaFileInput}
        />
        <Button
          type="button"
          variant="secondary"
          onClick={() => mediaFileRef.current?.click()}
          disabled={mediaBusy}
          className="gap-2 rounded-lg"
          data-testid={T.productMediaUpload}
        >
          {mediaBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {mediaBusy ? 'Mengunggah…' : 'Upload Gambar'}
        </Button>
      </div>

      <div className="flex gap-2">
        <Input
          value={mediaUrl}
          onChange={(e) => setMediaUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addFromUrl(); } }}
          placeholder="Tempel URL gambar… (otomatis diunduh ke penyimpanan lokal)"
          data-testid="admin-media-url-input"
        />
        <Button
          type="button"
          variant="secondary"
          onClick={addFromUrl}
          disabled={mediaBusy || !mediaUrl.trim()}
          data-testid={T.mediaAdd}
          className="shrink-0 gap-2 rounded-lg"
        >
          <Link2 className="h-4 w-4" /> Unduh & Tambah
        </Button>
      </div>

      {form.images.length ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {form.images.map((src, i) => (
            <div
              key={`${src}-${i}`}
              className="group relative overflow-hidden rounded-xl border border-border/70 bg-card"
              data-testid={T.productMediaTile}
              draggable
              onDragStart={(e) => { try { e.dataTransfer.setData('text/plain', String(i)); } catch (_) { /* noop */ } }}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const from = Number(e.dataTransfer.getData('text/plain'));
                if (Number.isNaN(from) || from === i) return;
                const next = [...form.images];
                const [it] = next.splice(from, 1);
                next.splice(i, 0, it);
                set({ images: next });
              }}
            >
              <span className="relative block aspect-square w-full bg-muted/40" style={CHECKER_STYLE}>
                <SmartImage
                  src={src}
                  alt={`Gambar produk ${i + 1}`}
                  className="absolute inset-0 h-full w-full"
                  fit="cover"
                />
              </span>
              {i === 0 ? (
                <span className="absolute left-1.5 top-1.5 rounded bg-black px-1.5 py-0.5 text-[10px] font-medium text-white">
                  Utama
                </span>
              ) : null}
              {!isLocalMedia(src) ? (
                <span className="absolute right-1.5 top-1.5 rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold text-amber-800">
                  EKSTERNAL
                </span>
              ) : null}
              <div className="flex items-center justify-between gap-1 border-t border-border/60 bg-card px-1.5 py-1.5">
                <div className="flex gap-0.5">
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7"
                    disabled={i === 0}
                    onClick={() => moveImage(i, -1)}
                    aria-label="Geser ke kiri"
                    data-testid={T.productMediaMoveLeft}
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7"
                    disabled={i === form.images.length - 1}
                    onClick={() => moveImage(i, 1)}
                    aria-label="Geser ke kanan"
                    data-testid={T.productMediaMoveRight}
                  >
                    <ChevronRight className="h-3.5 w-3.5" />
                  </Button>
                </div>
                <div className="flex gap-0.5">
                  {i !== 0 ? (
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7"
                      onClick={() => setPrimary(i)}
                      aria-label="Jadikan gambar utama"
                      data-testid={T.mediaSetPrimary}
                    >
                      <Star className="h-3.5 w-3.5" />
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="h-7 w-7 text-rose-600 hover:text-rose-700"
                    onClick={() => rmImage(i)}
                    aria-label="Hapus dari galeri"
                    data-testid={T.productMediaRemove}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-border bg-muted/30 px-4 py-10 text-center">
          <ImagePlus className="mx-auto h-7 w-7 text-muted-foreground" aria-hidden="true" />
          <p className="mt-2 text-sm font-medium text-foreground">Belum ada gambar produk</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Klik “Pilih dari Media Manager” untuk memakai gambar yang sudah ada, atau
            “Upload Gambar” untuk mengunggah dari perangkat Anda.
          </p>
        </div>
      )}

      <MediaPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        mode="multi"
        title="Pilih Gambar Produk"
        description="Pilih satu atau beberapa gambar dari pustaka media. Bisa juga langsung upload atau ambil dari URL."
        onConfirm={(assets) => addImages(assets.map((a) => a.url))}
      />
  </>
);
