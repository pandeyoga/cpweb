#!/usr/bin/env bash
# ============================================================================
#  Collector Parfum — UPDATE VPS + GANTI KATALOG (sekali jalan, aman diulang)
# ----------------------------------------------------------------------------
#  1. Backup database (mongodump) sebelum apa pun diubah
#  2. Ganti sumber repo git -> https://github.com/pandeyoga/cpweb (TANPA deploy ulang dari nol;
#     database, pesanan, media, .env & domain/SSL tetap)
#  3. Jalankan deploy.sh (git pull + build frontend + restart backend)
#  4. Cek katalog baru imports/catalog/produk.xlsx (Day/Night + brand) -> konfirmasi -> terapkan.
#     Harga & stok lama di database DIPERTAHANKAN untuk produk/SKU yang sama.
#
#  CARA PAKAI (di VPS sebagai root):
#     wget -O /root/vps_update_catalog.sh https://raw.githubusercontent.com/pandeyoga/cpweb/main/scripts/vps_update_catalog.sh
#     sudo bash /root/vps_update_catalog.sh
#
#  Opsi (env): ASSUME_YES=1 (tanpa tanya) · SKIP_DEPLOY=1 (hanya katalog) · SKIP_CATALOG=1 (hanya kode)
#              ALLOW_EMPTY=1 (tetap terapkan walau belum ada produk berharga -> toko kosong)
# ============================================================================
set -euo pipefail

APP_NAME="${APP_NAME:-collector-parfum}"
APP_USER="${APP_USER:-collector}"
APP_DIR="${APP_DIR:-/home/${APP_USER}/${APP_NAME}}"
REPO_URL="${REPO_URL:-https://github.com/pandeyoga/cpweb.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/${APP_NAME}}"
PY="${APP_DIR}/backend/venv/bin/python"
TS="$(date +%Y%m%d-%H%M%S)"

C_OFF='\033[0m'; C_G='\033[0;32m'; C_Y='\033[1;33m'; C_R='\033[0;31m'; C_B='\033[0;34m'
log()  { echo -e "${C_B}==>${C_OFF} $1"; }
ok()   { echo -e "${C_G}✓${C_OFF} $1"; }
warn() { echo -e "${C_Y}!${C_OFF} $1"; }
die()  { echo -e "${C_R}✗ $1${C_OFF}"; exit 1; }
confirm() { [[ "${ASSUME_YES:-0}" == "1" ]] && return 0; read -r -p "$1 [y/N] " a; [[ "${a}" =~ ^[Yy]$ ]]; }

[[ "${EUID}" -eq 0 ]] || die "Jalankan sebagai root: sudo bash $0"
[[ -d "${APP_DIR}/.git" ]] || die "Aplikasi tidak ditemukan di ${APP_DIR}. Untuk VPS baru pakai deploy.sh."
[[ -f "${APP_DIR}/backend/.env" ]] || die "${APP_DIR}/backend/.env tidak ada."

env_get() { grep -E "^$1=" "${APP_DIR}/backend/.env" | tail -1 | cut -d= -f2- | tr -d '"' || true; }
MONGO_URL="$(env_get MONGO_URL)"; DB_NAME="$(env_get DB_NAME)"
[[ -n "${MONGO_URL}" && -n "${DB_NAME}" ]] || die "MONGO_URL/DB_NAME kosong di backend/.env"

# ── 1. Backup database ──────────────────────────────────────────────────────
log "1/4 Backup database ${DB_NAME}"
mkdir -p "${BACKUP_DIR}"
if command -v mongodump >/dev/null 2>&1; then
  ARCHIVE="${BACKUP_DIR}/pre-update-${TS}.archive.gz"
  mongodump --quiet --uri="${MONGO_URL}" --db="${DB_NAME}" --gzip --archive="${ARCHIVE}"
  ok "Backup: ${ARCHIVE} ($(du -h "${ARCHIVE}" | cut -f1))"
  echo "    Pulihkan bila perlu: mongorestore --uri='${MONGO_URL}' --gzip --archive='${ARCHIVE}' --drop"
else
  warn "mongodump tidak ada — lanjut; replace_catalog.py tetap membuat backup server (Admin › Backup)."
fi

# ── 2 & 3. Ganti remote + deploy kode terbaru ──────────────────────────────
if [[ "${SKIP_DEPLOY:-0}" != "1" ]]; then
  log "2/4 Sumber repo -> ${REPO_URL} (${REPO_BRANCH})"
  git config --global --add safe.directory "${APP_DIR}" 2>/dev/null || true
  OLD="$(sudo -u "${APP_USER}" git -C "${APP_DIR}" remote get-url origin 2>/dev/null || echo '')"
  echo "    remote lama: ${OLD:-(tidak ada)}"
  sudo -u "${APP_USER}" git -C "${APP_DIR}" remote set-url origin "${REPO_URL}" 2>/dev/null \
    || sudo -u "${APP_USER}" git -C "${APP_DIR}" remote add origin "${REPO_URL}"
  sudo -u "${APP_USER}" git -C "${APP_DIR}" fetch --quiet origin "${REPO_BRANCH}" \
    || die "Gagal mengambil ${REPO_URL}. Pastikan repo sudah berisi kode terbaru (Save to GitHub) & publik."
  sudo -u "${APP_USER}" git -C "${APP_DIR}" reset --hard --quiet "origin/${REPO_BRANCH}"
  ok "Kode: $(sudo -u "${APP_USER}" git -C "${APP_DIR}" log -1 --pretty='%h %ad %s' --date=short)"

  log "3/4 Deploy (build frontend + restart backend) — domain/SSL memakai pilihan tersimpan"
  REPO_URL="${REPO_URL}" REPO_BRANCH="${REPO_BRANCH}" bash "${APP_DIR}/deploy.sh"
else
  warn "SKIP_DEPLOY=1 — langkah kode dilewati"
fi

# ── 4. Katalog baru ─────────────────────────────────────────────────────────
if [[ "${SKIP_CATALOG:-0}" == "1" ]]; then warn "SKIP_CATALOG=1 — katalog tidak diubah"; exit 0; fi
log "4/4 Katalog: cek imports/catalog/produk.xlsx (belum mengubah database)"
cd "${APP_DIR}"
set +e
sudo -u "${APP_USER}" "${PY}" scripts/replace_catalog.py; RC=$?
set -e
[[ ${RC} -eq 0 ]] || die "Validasi katalog gagal (lihat ERROR di atas). Database TIDAK diubah."

echo ""
echo "  Ringkasan di atas: 'active' = produk yang akan tampil (harga lama ditemukan),"
echo "  'variants_priced_from_existing_db' = varian yang memakai harga lama dari VPS."
confirm "Terapkan katalog baru ke database ${DB_NAME}?" || { warn "Dibatalkan — katalog tidak diubah."; exit 0; }
EXTRA=(); [[ "${ALLOW_EMPTY:-0}" == "1" ]] && EXTRA+=(--allow-empty-store)
set +e
sudo -u "${APP_USER}" "${PY}" scripts/replace_catalog.py --apply "${EXTRA[@]}"; RC=$?
set -e
if [[ ${RC} -eq 2 ]]; then
  die "Tidak ada produk berharga -> dibatalkan agar toko tidak kosong. Isi harga dulu, atau ulangi dengan ALLOW_EMPTY=1."
fi
[[ ${RC} -eq 0 ]] || die "replace_catalog.py gagal (kode ${RC})."

supervisorctl restart "${APP_NAME}-backend" >/dev/null && ok "Backend di-restart (indeks pencarian dimuat ulang)"
PORT="$(grep -oE '127\.0\.0\.1:[0-9]+' "/etc/supervisor/conf.d/${APP_NAME}-backend.conf" 2>/dev/null | head -1 | cut -d: -f2 || true)"
PORT="${PORT:-8003}"
for _ in $(seq 1 20); do curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1 && break; sleep 2; done
TOTAL="$(curl -fsSI "http://127.0.0.1:${PORT}/api/products?limit=1" 2>/dev/null | grep -i x-total-count | tr -dc '0-9')"
ok "Produk aktif di toko: ${TOTAL:-?}"
echo ""
echo -e "${C_G}SELESAI.${C_OFF} Cek toko & Admin › Produk. Laporan: ${APP_DIR}/imports/catalog/laporan_terakhir.json"
echo "  Produk tanpa harga tersimpan ARCHIVED — isi harga (Admin › Produk) lalu aktifkan."
echo "  Pasang domain setelah DNS mengarah ke VPS:  sudo DOMAIN=collectorparfum.com SETUP_SSL=yes bash ${APP_DIR}/deploy.sh"
