// pages/admin/AdminEmailLogsPage.js — log email transaksional ke pembeli (Sistem › Log Email).
import React from 'react';
import { PageHeader } from '../../components/admin/adminUi';
import EmailLogs from '../../components/admin/EmailLogs';
import { ContactMessages } from '../../components/admin/ContactMessages';

export default function AdminEmailLogsPage() {
  return (
    <div data-testid="admin-email-logs-page">
      <PageHeader title="Log Email" description="Email otomatis ke pembeli: konfirmasi lunas, pengingat batas bayar, pesanan dikirim & pembaruan resi." />
      <EmailLogs />
      <ContactMessages />
    </div>
  );
}
