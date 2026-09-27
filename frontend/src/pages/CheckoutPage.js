import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { MapPin, Truck, CreditCard, Wallet, Banknote, Tag, MessageSquare, ShieldCheck, Edit3, Check, X, Loader2, AlertTriangle, LogIn } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { RadioGroup, RadioGroupItem } from '../components/ui/radio-group';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import AddressDialog from '../components/checkout/AddressDialog';
import CheckoutSummary from '../components/checkout/CheckoutSummary';
import { useCart } from '../store/CartContext';
import { useAuth } from '../store/AuthContext';
import { useStoreSettings } from '../store/SettingsContext';
import { useCheckoutVoucher } from '../hooks/useCheckoutVoucher';
import { fetchShippingMethods, fetchPaymentMethods } from '../services/config';
import { listAddresses } from '../services/account';
import { createOrder } from '../services/orders';
import { track } from '../services/analytics';
import { formatIDR } from '../lib/format';
import { toast } from 'sonner';

const BLANK_ADDRESS = { name: '', phone: '', email: '', street: '', district: '', city: '', province: '', postal: '', label: 'Rumah' };
const ALL_GROUPS = ['online', 'transfer', 'ewallet']; // COD dihapus (E14); online = Midtrans
const newIdemKey = () => (window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);

const PAY_GROUP_LABEL = { online: 'Bayar Online', transfer: 'Transfer', ewallet: 'E-Wallet' };

export default function CheckoutPage() {
  const cart = useCart();
  const { user } = useAuth();
  const { settings } = useStoreSettings();
  const navigate = useNavigate();
  const idemKeyRef = React.useRef(newIdemKey()); // 1 kunci per isi checkout (anti order ganda)
  // Isi keranjang/voucher berubah → pesanan berbeda → kunci baru (server menolak key lama dgn isi lain).
  const cartSig = JSON.stringify([cart.items.map((i) => [i.key, i.quantity]), cart.voucher?.code || null]);
  React.useEffect(() => { idemKeyRef.current = newIdemKey(); }, [cartSig]);

  // Config dari API (SSOT backend) — bukan konstanta statis lagi.
  const [shippingMethods, setShippingMethods] = React.useState([]);
  const [paymentGroups, setPaymentGroups] = React.useState({ online: [], transfer: [], ewallet: [] });
  const PAY_GROUPS = ALL_GROUPS.filter((g) => paymentGroups[g]?.length);
  const [methodsLoading, setMethodsLoading] = React.useState(true);
  const [methodsError, setMethodsError] = React.useState(null);

  const [address, setAddress] = React.useState(BLANK_ADDRESS);
  const [addressDialogOpen, setAddressDialogOpen] = React.useState(false);
  const [shipping, setShipping] = React.useState(null);
  const [paymentTab, setPaymentTab] = React.useState('transfer');
  const [payment, setPayment] = React.useState(null);
  const [placing, setPlacing] = React.useState(false);
  const [stockError, setStockError] = React.useState(null);
  const placedRef = React.useRef(false); // cegah race redirect-keranjang setelah order sukses
  const beganRef = React.useRef(false); // Analytics E7: begin_checkout sekali
  React.useEffect(() => {
    if (beganRef.current || !cart.items.length) return;
    beganRef.current = true;
    track('begin_checkout', { meta: { items: cart.items.length, subtotal: cart.subtotal } });
  }, [cart.items.length, cart.subtotal]);

  // Prefill alamat dari alamat default tersimpan (login); fallback nama/telepon dari profil.
  React.useEffect(() => {
    if (!user) return;
    let active = true;
    (async () => {
      try {
        const addrs = await listAddresses();
        const def = addrs.find((a) => a.is_default) || addrs[0];
        if (active && def) {
          setAddress({
            name: def.name || user.name || '', phone: def.phone || user.phone || '', email: user.email || '',
            street: def.street || '', district: def.district || '', city: def.city || '',
            province: def.province || '', postal: def.postal || '', label: def.label || 'Rumah',
          });
          return;
        }
      } catch (e) { /* abaikan — pakai fallback */ }
      if (active) {
        setAddress((a) => ({ ...a, name: a.name || user.name || '', phone: a.phone || user.phone || '', email: a.email || user.email || '' }));
      }
    })();
    return () => { active = false; };
  }, [user]);

  // Redirect ke keranjang bila kosong (setelah hydrate) — kecuali baru saja checkout sukses.
  React.useEffect(() => {
    if (!placedRef.current && cart._hydrated && cart.items.length === 0) navigate('/keranjang', { replace: true });
  }, [cart._hydrated, cart.items.length, navigate]);

  // Muat metode kirim + bayar dari API.
  React.useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [ships, pays] = await Promise.all([fetchShippingMethods(), fetchPaymentMethods()]);
        if (!active) return;
        setShippingMethods(ships);
        setPaymentGroups(pays.grouped);
        setShipping(ships[0]?.id || null);
        const firstTab = ALL_GROUPS.find((g) => pays.grouped[g]?.length) || 'online';
        setPaymentTab(firstTab);
        setPayment(pays.grouped[firstTab]?.[0]?.id || null);
        setMethodsError(null);
      } catch (e) {
        if (active) setMethodsError('Gagal memuat opsi pengiriman/pembayaran. Muat ulang halaman.');
      } finally {
        if (active) setMethodsLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  const allPayments = React.useMemo(
    () => ALL_GROUPS.flatMap((g) => paymentGroups[g] || []),
    [paymentGroups],
  );
  const selectedShipping = shippingMethods.find((s) => s.id === shipping) || null;
  const selectedPayment = allPayments.find((m) => m.id === payment) || null;
  const codFee = 0;
  // Ongkir efektif — mirror tampilan dari SSOT backend pricing.effective_shipping.
  const freeThreshold = Number(settings?.free_shipping_threshold || 0);
  const freeShip = freeThreshold > 0 && cart.subtotal >= freeThreshold;
  const shipPrice = freeShip ? 0 : (selectedShipping?.price || 0);

  const {
    voucherCode, setVoucherCode, applying, voucherError, setVoucherError, checkoutDiscount,
    voucherCheck, voucherUnverified, recheck, applyVoucher, removeVoucher,
  } = useCheckoutVoucher(cart, shipPrice, selectedShipping);

  const total = Math.max(0, cart.subtotal - checkoutDiscount + shipPrice + codFee);

  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(address.email || '');
  const addressValid = address.name && address.phone && emailValid && address.street && address.city && address.province;

  const handlePlaceOrder = async () => {
    if (placing) return;
    setStockError(null);
    if (!addressValid) {
      toast.error('Lengkapi alamat pengiriman terlebih dahulu');
      setAddressDialogOpen(true);
      return;
    }
    if (!selectedShipping || !selectedPayment) {
      toast.error('Pilih metode pengiriman & pembayaran');
      return;
    }
    if (voucherUnverified) {
      toast.error('Diskon voucher belum terverifikasi', { description: 'Tekan "Validasi ulang" sebelum membuat pesanan.' });
      return;
    }
    setPlacing(true);
    try {
      const order = await createOrder({
        items: cart.items,
        address,
        shippingId: selectedShipping.id,
        payment: { group: selectedPayment.group, method_id: selectedPayment.id },
        voucherCode: cart.voucher?.code || null,
        note: cart.note,
        email: address.email,
        idempotencyKey: idemKeyRef.current,
      });
      cart.clear();
      placedRef.current = true;
      toast.success('Pesanan berhasil dibuat', { description: order.code });
      const t = (order.access_token ? `&t=${encodeURIComponent(order.access_token)}` : '')
        + (order.payment?.group === 'online' ? '&pay=1' : '');
      navigate(`/pesanan-sukses?code=${encodeURIComponent(order.code)}${t}`, { replace: true });
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      if (status === 409 && detail?.code === 'idempotency_conflict') {
        idemKeyRef.current = newIdemKey();
        toast.error('Isi pesanan berubah', { description: 'Periksa kembali ringkasan, lalu tekan Buat Pesanan sekali lagi.' });
      } else if (status === 409) {
        const d = detail || {};
        const line = cart.items.find((i) => i.productId === d.product_id && (
          (d.sku && i.sku === d.sku)
          || (Number(i.volumeMl) === Number(d.volume_ml) && (i.variantType || '') === (d.variant_type || ''))
        ));
        setStockError({
          name: line?.name || 'Salah satu produk',
          available: typeof d.available === 'number' ? d.available : null,
        });
        toast.error('Stok tidak mencukupi', {
          description: `${line?.name || 'Produk'} — tersisa ${d.available ?? 0}. Sesuaikan jumlah di keranjang.`,
        });
      } else if (status === 400) {
        const msg = typeof detail === 'string' ? detail : 'Pesanan tidak dapat diproses';
        setVoucherError(/voucher/i.test(msg) ? msg : null);
        toast.error(msg);
      } else if (status === 422) {
        toast.error('Data checkout tidak valid. Periksa kembali isian Anda.');
      } else {
        toast.error('Terjadi kesalahan. Coba lagi sebentar.');
      }
    } finally {
      setPlacing(false);
    }
  };

  if (methodsLoading) {
    return (
      <div className="cp-container cp-section" data-testid="checkout-page">
        <div className="flex items-center justify-center py-24 text-black/50">
          <Loader2 className="h-6 w-6 animate-spin mr-2" /> Memuat checkout…
        </div>
      </div>
    );
  }

  return (
    <div className="cp-container cp-section" data-testid="checkout-page">
      <div className="mb-8">
        <div className="cp-eyebrow">Checkout</div>
        <h1 className="cp-headline text-4xl sm:text-5xl mt-2">Selesaikan pesanan Anda.</h1>
        {!user && (
          <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-[color:var(--cp-paper-fog)] px-4 py-1.5 text-[12px] text-black/70">
            <LogIn className="h-3.5 w-3.5" /> Checkout sebagai tamu —
            <Link to="/akun" className="underline font-medium">masuk</Link> agar pesanan tersimpan di riwayat.
          </div>
        )}
      </div>

      {methodsError && (
        <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700" data-testid="checkout-methods-error">
          {methodsError}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8">
        <div className="lg:col-span-8 space-y-4 lg:space-y-6">
          {/* Alamat */}
          <div className="rounded-2xl border-l-4 border-l-[color:var(--cp-market-blue)] border border-black/10 bg-[color:var(--cp-paper-warm)] p-5 sm:p-6" data-testid="checkout-address-card">
            <div className="flex items-center gap-3 mb-4">
              <MapPin className="h-5 w-5 text-[color:var(--cp-market-blue)]" />
              <div className="cp-mono uppercase text-[11px] tracking-[0.22em]">Alamat Pengiriman</div>
              <button
                onClick={() => setAddressDialogOpen(true)}
                data-testid="checkout-change-address-button"
                className="ml-auto text-sm text-[color:var(--cp-market-blue)] hover:underline cp-mono uppercase text-[11px] tracking-[0.22em] inline-flex items-center gap-1"
              >
                <Edit3 className="h-3.5 w-3.5" /> {addressValid ? 'Ubah' : 'Isi Alamat'}
              </button>
            </div>
            {addressValid ? (
              <div className="flex items-start gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="font-semibold text-sm">{address.name}</div>
                    <div className="cp-mono text-xs text-black/60">{address.phone}</div>
                    <div className="cp-mono text-xs text-black/60" data-testid="checkout-address-email">{address.email}</div>
                    <span className="cp-mono uppercase text-[10px] tracking-[0.22em] bg-[color:var(--cp-market-blue-soft)] text-[color:var(--cp-market-blue)] px-2 py-0.5 rounded-full">{address.label}</span>
                  </div>
                  <div className="text-sm text-black/75 mt-1 leading-relaxed">
                    {address.street}{address.district ? `, ${address.district}` : ''}, {address.city}, {address.province} {address.postal}
                  </div>
                </div>
              </div>
            ) : (
              <button onClick={() => setAddressDialogOpen(true)} className="w-full text-left text-sm text-black/60 rounded-xl border border-dashed border-black/20 px-4 py-4 hover:border-[color:var(--cp-market-blue)]">
                Belum ada alamat. Klik untuk mengisi alamat pengiriman.
              </button>
            )}
          </div>

          {/* Stok error banner */}
          {stockError && (
            <div className="rounded-2xl border border-amber-300 bg-amber-50 p-4 flex items-start gap-3" data-testid="checkout-stock-error">
              <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5" />
              <div className="text-sm text-amber-800">
                <div className="font-semibold">Stok tidak mencukupi</div>
                <div>{stockError.name}{stockError.available != null ? ` — tersisa ${stockError.available}.` : '.'} Sesuaikan jumlah di <Link to="/keranjang" className="underline">keranjang</Link>.</div>
              </div>
            </div>
          )}

          {/* Produk Ringkasan */}
          <div className="rounded-2xl border border-black/10 bg-[color:var(--cp-paper-warm)] overflow-hidden" data-testid="checkout-items-card">
            <div className="px-5 sm:px-6 py-4 border-b border-black/10 flex items-center gap-2">
              <div className="h-8 w-8 rounded-full bg-[color:var(--cp-paper-fog)] flex items-center justify-center">
                <ShieldCheck className="h-4 w-4" />
              </div>
              <div>
                <div className="font-semibold text-sm">Collector Parfum</div>
                <div className="cp-mono uppercase text-[10px] tracking-[0.22em] text-black/60">Toko Resmi</div>
              </div>
            </div>
            {cart.items.map((it) => (
              <div key={it.key} className="px-5 sm:px-6 py-4 border-b border-black/5 last:border-0 flex items-center gap-4" data-testid="checkout-item">
                <div className="h-16 w-14 rounded-lg overflow-hidden bg-[color:var(--cp-paper-fog)] flex-shrink-0">
                  <img src={it.image} alt={it.name} className="h-full w-full object-cover" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{it.name}</div>
                  <div className="cp-mono uppercase text-[10px] tracking-[0.22em] text-black/55 mt-1">{it.variantLabel || `${it.concentration ? it.concentration + ' · ' : ''}${it.variantType ? it.variantType + ' · ' : ''}${it.volumeMl}ml`}</div>
                </div>
                <div className="text-right">
                  <div className="cp-mono text-xs text-black/55">x{it.quantity}</div>
                  <div className="cp-mono text-sm font-semibold">{formatIDR(it.unitPrice * it.quantity)}</div>
                </div>
              </div>
            ))}

            {/* Voucher + catatan */}
            <div className="px-5 sm:px-6 py-4 border-t border-black/10 grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <Tag className="h-4 w-4 text-[color:var(--cp-market-blue)]" />
                  <Input
                    placeholder="Kode voucher"
                    value={voucherCode}
                    onChange={(e) => setVoucherCode(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') applyVoucher(); }}
                    className="h-10 rounded-full bg-white"
                    data-testid="checkout-voucher-input"
                    aria-describedby="checkout-voucher-error"
                  />
                  {cart.voucher ? (
                    <Button onClick={removeVoucher} variant="outline" className="rounded-full h-10 border-red-200 text-red-600 hover:bg-red-50" data-testid="checkout-voucher-remove-button">
                      <X className="h-4 w-4 mr-1" /> Hapus
                    </Button>
                  ) : (
                    <Button onClick={applyVoucher} disabled={applying || !voucherCode.trim()} variant="outline" className="rounded-full h-10 disabled:opacity-60" data-testid="checkout-voucher-apply-button">
                      {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Pakai'}
                    </Button>
                  )}
                </div>
                {voucherError && (
                  <div id="checkout-voucher-error" className="mt-1.5 text-[12px] text-red-600" data-testid="checkout-voucher-error">{voucherError}</div>
                )}
                {voucherUnverified && voucherCheck === 'error' && (
                  <div className="mt-1.5 flex items-center gap-2 text-[12px] text-amber-700" data-testid="checkout-voucher-unverified">
                    Total dengan voucher belum terverifikasi.
                    <button type="button" className="underline" onClick={recheck} data-testid="checkout-voucher-recheck">
                      Validasi ulang
                    </button>
                  </div>
                )}
                {cart.voucher && !voucherError && (
                  <div className="mt-1.5 inline-flex items-center gap-1 cp-mono uppercase text-[10px] tracking-[0.2em] text-[color:var(--cp-brass)]" data-testid="checkout-voucher-applied">
                    <Check className="h-3 w-3" /> {cart.voucher.code} · {cart.voucher.label}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-black/50" />
                <Textarea
                  placeholder="Catatan untuk penjual (opsional)"
                  value={cart.note}
                  onChange={(e) => cart.setNote(e.target.value)}
                  className="min-h-[40px] rounded-2xl bg-white"
                  data-testid="checkout-seller-note-textarea"
                />
              </div>
            </div>
          </div>

          {/* Kurir */}
          <div className="rounded-2xl border border-black/10 bg-[color:var(--cp-paper-warm)] p-5 sm:p-6" data-testid="checkout-shipping-card">
            <div className="flex items-center gap-2 mb-4">
              <Truck className="h-5 w-5 text-[color:var(--cp-market-blue)]" />
              <div className="cp-mono uppercase text-[11px] tracking-[0.22em]">Opsi Pengiriman</div>
            </div>
            {freeThreshold > 0 && (
              <div className="mb-3 text-xs text-black/60" data-testid="checkout-free-shipping-note">
                {freeShip ? 'Selamat! Anda mendapat gratis ongkir.' : `Gratis ongkir untuk belanja min. ${formatIDR(freeThreshold)}.`}
              </div>
            )}
            <RadioGroup value={shipping || ''} onValueChange={setShipping} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {shippingMethods.map((s) => {
                const active = shipping === s.id;
                return (
                  <label key={s.id} htmlFor={`ship-${s.id}`} data-testid="checkout-shipping-option"
                    className={`flex items-center gap-3 p-3 rounded-2xl border cursor-pointer transition-colors ${active ? 'border-[color:var(--cp-market-blue)] bg-[color:var(--cp-market-blue-soft)]' : 'border-black/10 hover:border-black/25 bg-white'}`}>
                    <RadioGroupItem id={`ship-${s.id}`} value={s.id} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium">{s.name}</div>
                      <div className="cp-mono uppercase text-[10px] tracking-[0.22em] text-black/60">Estimasi {s.eta}</div>
                    </div>
                    <div className="cp-mono text-sm font-semibold">{(s.price === 0 || freeShip) ? 'GRATIS' : formatIDR(s.price)}</div>
                  </label>
                );
              })}
            </RadioGroup>
          </div>

          {/* Pembayaran */}
          <div className="rounded-2xl border border-black/10 bg-[color:var(--cp-paper-warm)] p-5 sm:p-6" data-testid="checkout-payment-card">
            <div className="flex items-center gap-2 mb-4">
              <CreditCard className="h-5 w-5 text-[color:var(--cp-market-blue)]" />
              <div className="cp-mono uppercase text-[11px] tracking-[0.22em]">Metode Pembayaran</div>
            </div>
            <Tabs value={paymentTab} onValueChange={(v) => { setPaymentTab(v); setPayment(paymentGroups[v]?.[0]?.id || null); }}>
              <TabsList className="bg-[color:var(--cp-paper-fog)] rounded-full h-11 p-1">
                {PAY_GROUPS.map((g) => (
                  <TabsTrigger key={g} value={g} disabled={!paymentGroups[g]?.length}
                    data-testid={`checkout-payment-tab-${g}`}
                    className="rounded-full data-[state=active]:bg-[color:var(--cp-ink)] data-[state=active]:text-[color:var(--cp-paper)] cp-mono uppercase text-[10px] tracking-[0.22em]">
                    {PAY_GROUP_LABEL[g]}
                  </TabsTrigger>
                ))}
              </TabsList>
              {PAY_GROUPS.map((key) => (
                <TabsContent key={key} value={key} className="pt-4">
                  <RadioGroup value={payment || ''} onValueChange={setPayment} className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {(paymentGroups[key] || []).map((m) => {
                      const active = payment === m.id;
                      return (
                        <label key={m.id} htmlFor={`pay-${m.id}`} data-testid="checkout-payment-option"
                          className={`flex items-center gap-3 p-3 rounded-2xl border cursor-pointer transition-colors ${active ? 'border-[color:var(--cp-market-blue)] bg-[color:var(--cp-market-blue-soft)]' : 'border-black/10 hover:border-black/25 bg-white'}`}>
                          <RadioGroupItem id={`pay-${m.id}`} value={m.id} />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium">{m.name}</div>
                            {m.extra && (
                              <div className="cp-mono uppercase text-[10px] tracking-[0.22em] text-black/60">{m.extra}</div>
                            )}
                          </div>
                          {key === 'transfer' && <Banknote className="h-4 w-4 text-black/40" />}
                          {key === 'online' && <CreditCard className="h-4 w-4 text-black/40" />}
                          {key === 'ewallet' && <Wallet className="h-4 w-4 text-black/40" />}
                        </label>
                      );
                    })}
                  </RadioGroup>
                </TabsContent>
              ))}
            </Tabs>
          </div>
        </div>

        {/* Summary */}
        <CheckoutSummary
          cart={cart}
          checkoutDiscount={checkoutDiscount}
          selectedShipping={selectedShipping}
          shipPrice={shipPrice}
          codFee={codFee}
          total={total}
          placing={placing}
          canPlace={cart.items.length > 0 && !!selectedShipping && !!selectedPayment}
          onPlaceOrder={handlePlaceOrder}
        />
      </div>

      <AddressDialog
        open={addressDialogOpen}
        onOpenChange={setAddressDialogOpen}
        address={address}
        onSave={(a) => { setAddress(a); toast.success('Alamat diperbarui'); }}
      />
    </div>
  );
}
