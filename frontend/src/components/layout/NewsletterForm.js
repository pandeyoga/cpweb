// components/layout/NewsletterForm.js — opt-in newsletter yang disimpan di server (bukan konfirmasi palsu).
import React, { useState } from 'react';
import { toast } from 'sonner';
import { subscribeNewsletter } from '../../services/forms';

export const NewsletterForm = () => {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    try {
      await subscribeNewsletter(email.trim());
      toast.success('Terima kasih! Email Anda sudah terdaftar.');
      setEmail('');
    } catch (err) {
      toast.error('Email tidak valid atau server sedang bermasalah. Coba lagi.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="flex items-center gap-2 border border-white/20 rounded-full pl-4 pr-1 py-1" data-testid="footer-newsletter-form">
      <input
        type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
        placeholder="email@anda.com" aria-label="Email untuk newsletter" data-testid="footer-newsletter-input"
        className="bg-transparent placeholder:text-white/40 text-sm outline-none flex-1 py-2"
      />
      <button type="submit" disabled={busy}
        className="bg-[color:var(--cp-paper)] text-[color:var(--cp-ink)] rounded-full text-xs cp-mono uppercase tracking-[0.2em] px-4 py-2 disabled:opacity-50"
        data-testid="footer-newsletter-submit">
        {busy ? '...' : 'Daftar'}
      </button>
    </form>
  );
};
