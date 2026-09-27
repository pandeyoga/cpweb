// components/admin/ShipDialog.js — input kurir + nomor resi saat kirim / koreksi resi (E16).
import React, { useEffect, useState } from 'react';
import { Loader2, Truck } from 'lucide-react';
import { listCouriers } from '../../services/admin';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';

// Tebak kurir dari metode ongkir yang dipilih pembeli (mis. "jne-reg" → JNE).
const guessCourier = (couriers, order) => {
  const hay = `${order?.shipping?.method_id || ''} ${order?.shipping?.name || ''}`.toLowerCase();
  return (couriers.find((c) => c.keywords.some((k) => hay.includes(k))) || couriers[couriers.length - 1])?.id || '';
};

export default function ShipDialog({ open, onOpenChange, order, onSubmit, edit = false }) {
  const [couriers, setCouriers] = useState([]);
  const [courier, setCourier] = useState('');
  const [resi, setResi] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (open && !couriers.length) listCouriers().then(setCouriers).catch(() => {}); }, [open, couriers.length]);
  useEffect(() => {
    if (!open || !couriers.length) return;
    setCourier(order?.shipment?.courier || guessCourier(couriers, order));
    setResi(order?.shipment?.tracking_number || '');
  }, [open, couriers, order]);

  const valid = /^[A-Za-z0-9-]{6,40}$/.test(resi.replace(/\s+/g, '')) && courier;
  const submit = async (e) => {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    try { await onSubmit(courier, resi.replace(/\s+/g, '')); onOpenChange(false); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="admin-ship-dialog">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base"><Truck className="h-4 w-4" /> {edit ? 'Ubah Nomor Resi' : 'Kirim Pesanan'}</DialogTitle>
            <DialogDescription>{edit ? 'Pembeli otomatis menerima email berisi resi yang baru.' : 'Nomor resi wajib diisi. Pembeli otomatis menerima email berisi resi & link lacak.'}</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label>Kurir</Label>
            <Select value={courier} onValueChange={setCourier}>
              <SelectTrigger data-testid="admin-ship-courier-select"><SelectValue placeholder="Pilih kurir" /></SelectTrigger>
              <SelectContent>{couriers.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ship-resi">Nomor Resi</Label>
            <Input id="ship-resi" value={resi} onChange={(e) => setResi(e.target.value)} placeholder="mis. JP1234567890" autoFocus className="font-mono" data-testid="admin-ship-resi-input" />
            {resi && !valid ? <p className="text-xs text-rose-600" data-testid="admin-ship-resi-error">6–40 karakter huruf/angka.</p> : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Batal</Button>
            <Button type="submit" disabled={!valid || busy} className="gap-2" data-testid="admin-ship-submit">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}{edit ? 'Simpan & Kirim Email' : 'Tandai Dikirim'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
