import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Textarea } from '../../ui/textarea';
import { Switch } from '../../ui/switch';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../../ui/dialog';
import { MediaField } from '../media/MediaField';
import { upsertBrand } from '../../../services/admin';

export const BrandDialog = ({ brand, onClose, onSaved }) => {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (brand) setForm({ logo: brand.logo || '', image: brand.image || '', desc: brand.desc || '', order: brand.order || 0, hidden: !!brand.hidden });
  }, [brand]);
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      await upsertBrand({ name: brand.name, ...form, order: Number(form.order) || 0 });
      toast.success('Brand disimpan.');
      onSaved();
    } catch (e) { toast.error(e?.response?.data?.detail || 'Gagal menyimpan.'); } finally { setSaving(false); }
  };

  return (
    <Dialog open={!!brand} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Brand: {brand?.name}</DialogTitle>
          <DialogDescription>Nama brand mengikuti data produk. Logo transparan (SVG/PNG) paling rapi.</DialogDescription>
        </DialogHeader>
        {form ? (
          <div className="space-y-4">
            <MediaField label="Logo (SVG/PNG transparan)" value={form.logo} onChange={set('logo')} testId="admin-brand-logo" previewClassName="h-20 w-20" pickerTitle="Pilih Logo" />
            <MediaField label="Foto kartu (opsional, rasio 4:3)" value={form.image} onChange={set('image')} testId="admin-brand-image" previewClassName="h-20 w-28" pickerTitle="Pilih Foto" hint="Tanpa foto, kartu menampilkan kipas botol produk brand ini." />
            <div className="space-y-1.5"><Label>Deskripsi singkat</Label><Textarea rows={2} value={form.desc} onChange={(e) => set('desc')(e.target.value)} data-testid="admin-brand-desc" /></div>
            <div className="grid grid-cols-2 gap-3 items-end">
              <div className="space-y-1.5"><Label>Urutan (1 = paling depan, 0 = otomatis)</Label><Input type="number" min={0} value={form.order} onChange={(e) => set('order')(e.target.value)} data-testid="admin-brand-order" /></div>
              <label className="flex items-center gap-2 text-sm pb-2"><Switch checked={form.hidden} onCheckedChange={set('hidden')} data-testid="admin-brand-hidden" /> Sembunyikan</label>
            </div>
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>Batal</Button>
          <Button onClick={save} disabled={saving} data-testid="admin-brand-save">{saving ? 'Menyimpan…' : 'Simpan'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
