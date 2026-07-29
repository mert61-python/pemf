#!/usr/bin/env bash
# =============================================================================
# PEMF native macOS backend build — base.zip / base-linux.zip'in macOS karşılığı.
# .github/workflows/linux-backend.yml'in birebir yerel (Mac'te çalışan) eşleniği.
#
# NEDEN MAC'TE ZORUNLU: PyInstaller cross-compile YAPMAZ. Ubuntu'da build edilirse
# ELF çıkar, Mac'te çalışmaz. Bu betik macOS'ta (tercihen Apple Silicon) koşmalı.
#
# Kullanım:
#   ./build_mac.sh                 # tam build (bağımlılık + frontend + paketleme)
#   ./build_mac.sh --skip-deps     # .venv-mac hazırsa pip adımını atla
#   ./build_mac.sh --skip-frontend # frontend/dist hazırsa expo export'u atla
#
# Çıktı:  base-mac.zip  +  base-mac.sha256.txt   (proje kökünde)
#
# Opsiyonel imzalama (Developer ID keychain'de kuruluysa):
#   PEMF_CODESIGN_ID="Developer ID Application: ... (TEAMID)" ./build_mac.sh
# =============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

VENV=".venv-mac"
# Windows build'i dist/PEMF_Backend/PEMF_Backend.exe olarak burada duruyor.
# ÜSTÜNE YAZMAMAK için mac çıktısı ayrı dizine gider.
DIST_DIR="dist-mac"
WORK_DIR="build-mac"
OUT_ZIP="base-mac.zip"

SKIP_DEPS=0
SKIP_FRONTEND=0
for arg in "$@"; do
  case "$arg" in
    --skip-deps)     SKIP_DEPS=1 ;;
    --skip-frontend) SKIP_FRONTEND=1 ;;
    *) echo "Bilinmeyen argüman: $arg" >&2; exit 2 ;;
  esac
done

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31m[HATA] %s\033[0m\n' "$*" >&2; exit 1; }

# --- 0) Ön koşullar -----------------------------------------------------------
say "0/7  Ön koşul kontrolü"
[[ "$(uname -s)" == "Darwin" ]] || die "Bu betik macOS içindir (uname=$(uname -s)). Linux için .github/workflows/linux-backend.yml kullanın."
command -v brew >/dev/null || die "Homebrew yok. Kur: https://brew.sh"

BREW_PREFIX="$(brew --prefix)"
PY310="$BREW_PREFIX/opt/python@3.10/bin/python3.10"
[[ -x "$PY310" ]] || die "python@3.10 yok. Kur: brew install python@3.10
  (Sürüm KİLİTLİ: requirements.txt CPython 3.10 venv'ine göre pinlenmiş; 3.11+ ile torch 2.1.2 wheel'i yok.)"

# sqlcipher3 0.6.2 macOS arm64 için PREBUILT wheel yayımlıyor (SQLCipher gömülü) —
# bu makinede doğrulandı: derleme gerekmiyor, şifreleme gerçek. brew sqlcipher yalnız
# wheel bulunamayıp kaynaktan derleme gerekirse (x86_64 / farklı Python) lazım olur.
SQLCIPHER_PREFIX="$BREW_PREFIX/opt/sqlcipher"
if [[ ! -d "$SQLCIPHER_PREFIX" ]]; then
  echo "  [not] brew sqlcipher yok — prebuilt wheel varsa sorun değil."
  echo "        Kaynaktan derleme hatası alırsanız: brew install sqlcipher"
fi

command -v npm >/dev/null || die "node/npm yok. Kur: brew install node"

echo "  python@3.10 : $($PY310 --version)"
echo "  sqlcipher   : $("$SQLCIPHER_PREFIX/bin/sqlcipher" --version 2>/dev/null || echo 'kurulu')"
echo "  node/npm    : $(node --version) / $(npm --version)"
echo "  mimari      : $(uname -m)"

# --- 1) venv ------------------------------------------------------------------
say "1/7  Python 3.10 venv ($VENV)"
[[ -d "$VENV" ]] || "$PY310" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip wheel >/dev/null

# --- 2) Bağımlılıklar ---------------------------------------------------------
if [[ "$SKIP_DEPS" == "0" ]]; then
  say "2/7  Bağımlılıklar (requirements.txt → macOS uyarlaması)"
  # requirements.txt DEĞİŞTİRİLMEZ. macOS için iki uyarlama gerekiyor:
  #   1. torch==2.1.2+cpu / torchvision==0.16.2+cpu → "+cpu" yerel-sürüm etiketli
  #      wheel'ler yalnız Linux/Windows için üretilir; macOS arm64 wheel'i PyPI'de
  #      düz "2.1.2" adıyla durur (zaten CPU-only, macOS'ta CUDA yok).
  #   2. download.pytorch.org/whl/cpu ek-index'i macOS arm64 sunmaz → çıkarılır.
  REQ_MAC="$(mktemp -t pemf-req-mac).txt"
  sed -e 's/^torch==2\.1\.2+cpu/torch==2.1.2/' \
      -e 's/^torchvision==0\.16\.2+cpu/torchvision==0.16.2/' \
      -e 's|^--extra-index-url https://download.pytorch.org/whl/cpu|# (macOS: torch PyPI’den, CPU-only)|' \
      requirements.txt > "$REQ_MAC"

  # sqlcipher3 için kaynaktan-derleme yedeği: brew sqlcipher keg-only olduğundan
  # başlık/kütüphane yolları elle verilmeli. Prebuilt wheel gelirse bunlar kullanılmaz.
  if [[ -d "$SQLCIPHER_PREFIX" ]]; then
    export LDFLAGS="-L$SQLCIPHER_PREFIX/lib ${LDFLAGS:-}"
    export CPPFLAGS="-I$SQLCIPHER_PREFIX/include ${CPPFLAGS:-}"
    export PKG_CONFIG_PATH="$SQLCIPHER_PREFIX/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
  fi

  pip install -r "$REQ_MAC"
  rm -f "$REQ_MAC"
else
  say "2/7  Bağımlılıklar ATLANDI (--skip-deps)"
fi

# --- 3) sqlcipher3 doğrulaması (at-rest şifreleme) ---------------------------
# Spec dosyası sqlcipher3 bundle edilemezse build'i KIRIYOR. Aynı garantiyi burada
# ÖNCEDEN veriyoruz: 40 dakikalık PyInstaller turundan sonra değil, saniyeler içinde.
say "3/7  sqlcipher3 gerçek-şifreleme doğrulaması"
python - <<'PY'
import os, tempfile, sys
from sqlcipher3 import dbapi2 as sq
p = os.path.join(tempfile.mkdtemp(), "t.db")
c = sq.connect(p); c.execute("PRAGMA key='x'"); c.execute("CREATE TABLE t(a)")
c.execute("INSERT INTO t VALUES ('HASTA_PII')"); c.commit(); c.close()
raw = open(p, "rb").read()
if raw.startswith(b"SQLite format 3") or b"HASTA_PII" in raw:
    sys.exit("[FAIL] DB DÜZ METİN — sqlcipher3 sistem sqlite'ına derlenmiş, SQLCipher'a değil.")
print("  [OK] DB şifreli (SQLite başlığı yok, PII düz metin değil)")
PY

# --- 4) Frontend (Expo web export) -------------------------------------------
# Spec 'frontend/dist' arar; bu depoda Expo kaynağı 'pf/' altında ve export
# 'pf/dist' üretir (bkz. Dockerfile.frontend). Export'u spec'in beklediği yere
# sahneliyoruz. frontend/dist YOKSA spec sessizce atlar → backend web arayüzsüz
# çıkar; bu yüzden adım sonunda varlığı DOĞRULANIR.
if [[ "$SKIP_FRONTEND" == "0" ]]; then
  say "4/7  Frontend web export (pf → frontend/dist)"
  [[ -d pf ]] || die "pf/ (Expo frontend) yok."
  ( cd pf && npm ci --legacy-peer-deps && npm run export:web )
  rm -rf frontend/dist
  mkdir -p frontend
  cp -R pf/dist frontend/dist
else
  say "4/7  Frontend ATLANDI (--skip-frontend)"
fi
[[ -f frontend/dist/index.html ]] || die "frontend/dist/index.html yok → backend web arayüzü OLMADAN paketlenir. Export'u --skip-frontend'siz çalıştırın."

# --- 5) PyInstaller -----------------------------------------------------------
say "5/7  PyInstaller onedir build (birkaç on dakika)"
# Modeller EXE'ye GÖMÜLMEZ: yayındaki Windows base.zip de içermiyor (doğrulandı: 6191
# dosya, sıfır ai_models girdisi). Modeller launcher'ın ayrıca indirdiği profil
# paketlerinden gelir. Gömseydik mac base'i ~3.4 GB olur ve kullanıcı aynı modelleri
# ikinci kez indirirdi. Gömmek isterseniz: PEMF_EMBED_MODELS=1 ./build_mac.sh
export PEMF_EMBED_MODELS="${PEMF_EMBED_MODELS:-0}"
echo "  PEMF_EMBED_MODELS=$PEMF_EMBED_MODELS"
rm -rf "$DIST_DIR" "$WORK_DIR"
python -m PyInstaller build_tools/PEMF_Backend_onedir.spec \
  --noconfirm --distpath "$DIST_DIR" --workpath "$WORK_DIR"

APP_BIN="$DIST_DIR/PEMF_Backend/PEMF_Backend"
[[ -f "$APP_BIN" ]] || die "Mach-O binary üretilmedi: $APP_BIN"
file "$APP_BIN" | grep -q "Mach-O" || die "Üretilen dosya Mach-O değil: $(file "$APP_BIN")"

# --- 6) İmzalama + smoke ------------------------------------------------------
say "6/7  İmzalama + smoke test"
if [[ -n "${PEMF_CODESIGN_ID:-}" ]]; then
  echo "  Developer ID ile imzalanıyor: $PEMF_CODESIGN_ID"
  codesign --force --deep --timestamp --options runtime \
           --sign "$PEMF_CODESIGN_ID" "$DIST_DIR/PEMF_Backend"
  codesign --verify --deep --strict "$DIST_DIR/PEMF_Backend" && echo "  [OK] imza doğrulandı"
else
  echo "  PEMF_CODESIGN_ID verilmedi → PyInstaller'ın ad-hoc imzası kullanılacak."
  echo "  (Gatekeeper: kullanıcı ZIP'i indirince karantina uygulanır. Notarization"
  echo "   .dmg launcher tarafında ayrıca yapılır.)"
fi

# Smoke: süreç ayağa kalkıp import zincirini geçiyor mu? (--help yoksa kısa çalıştırıp öldür)
set +e
"$APP_BIN" --help >/dev/null 2>&1
rc=$?
set -e
[[ $rc -eq 0 ]] && echo "  [OK] --help geçti" || echo "  (--help desteklenmiyor olabilir; asıl smoke: kurulumda --port 8000)"

# --- 7) Paketle ---------------------------------------------------------------
say "7/7  Paketleme → $OUT_ZIP"
rm -f "$OUT_ZIP" "base-mac.sha256.txt"
( cd "$DIST_DIR" && zip -rqy "../$OUT_ZIP" PEMF_Backend )   # -y: sembolik linkleri KORU (framework'ler için şart)
shasum -a 256 "$OUT_ZIP" | tee base-mac.sha256.txt

printf '\n\033[1;32m✓ BİTTİ\033[0m  %s (%s)\n' "$OUT_ZIP" "$(du -h "$OUT_ZIP" | cut -f1)"
cat <<EOF

Sıradaki adımlar (yayın):
  1. base-mac.zip → GitHub release 'client-app-v$(cat VERSION 2>/dev/null || echo X.Y.Z)' varlıklarına yükle
  2. pemf-app-packages/manifest.json → 'base_mac' bloğu ekle (url + yukarıdaki sha256 + size)
  3. pemf-vet-web/src/config.ts → macosReady: true
  4. Vercel deploy → mac istemcisi sitede canlı
EOF
