// hooks/useCheckoutVoucher.js — voucher di checkout: validasi server DENGAN ongkir aktual.
// Butir 18: bila validasi ulang gagal (jaringan) setelah keranjang/ongkir berubah, total ditandai
// BELUM terverifikasi (voucherUnverified) dan pembeli diminta "Validasi ulang" sebelum membuat pesanan.
import React from 'react';
import { toast } from 'sonner';
import { validateVoucher } from '../services/vouchers';

export const useCheckoutVoucher = (cart, shipPrice, selectedShipping) => {
  const [voucherCode, setVoucherCode] = React.useState(cart.voucher ? cart.voucher.code : '');
  const [applying, setApplying] = React.useState(false);
  const [voucherError, setVoucherError] = React.useState(null);
  const [checkoutDiscount, setCheckoutDiscount] = React.useState(cart.voucher?.discount || 0);
  const [voucherCheck, setVoucherCheck] = React.useState('checking'); // 'ok' | 'checking' | 'error'
  const [tick, setTick] = React.useState(0);

  React.useEffect(() => {
    const code = cart.voucher?.code;
    if (!code || !selectedShipping) {
      if (!code) { setCheckoutDiscount(0); setVoucherError(null); setVoucherCheck('ok'); }
      return undefined;
    }
    let active = true;
    setVoucherCheck('checking');
    validateVoucher({ code, subtotal: cart.subtotal, shipping: shipPrice, items: cart.items })
      .then((res) => {
        if (!active) return;
        if (res.valid) { setCheckoutDiscount(res.discount); setVoucherError(null); }
        else { setCheckoutDiscount(0); setVoucherError(res.reason || 'Voucher tidak berlaku'); cart.removeVoucher(); }
        setVoucherCheck('ok');
      })
      .catch(() => { if (active) setVoucherCheck('error'); });
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cart.voucher?.code, cart.subtotal, shipPrice, selectedShipping, tick]);

  const applyVoucher = async () => {
    const code = String(voucherCode || '').trim();
    if (!code) return;
    setApplying(true);
    setVoucherError(null);
    try {
      const res = await validateVoucher({ code, subtotal: cart.subtotal, shipping: shipPrice, items: cart.items });
      if (res.valid) {
        cart.applyVoucher(res);
        setCheckoutDiscount(res.discount);
        toast.success('Voucher diterapkan', { description: res.label });
      } else {
        setVoucherError(res.reason || 'Voucher tidak valid');
        toast.error(res.reason || 'Voucher tidak valid');
      }
    } catch (e) {
      setVoucherError('Gagal memvalidasi voucher. Coba lagi.');
      toast.error('Gagal memvalidasi voucher');
    } finally {
      setApplying(false);
    }
  };

  const removeVoucher = () => {
    cart.removeVoucher();
    setVoucherCode('');
    setCheckoutDiscount(0);
    setVoucherError(null);
    toast.message('Voucher dihapus');
  };

  return {
    voucherCode, setVoucherCode, applying, voucherError, setVoucherError, checkoutDiscount, voucherCheck,
    voucherUnverified: !!cart.voucher && voucherCheck !== 'ok', recheck: () => setTick((n) => n + 1),
    applyVoucher, removeVoucher,
  };
};
