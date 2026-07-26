#!/usr/bin/env bash
# =============================================================================
# PEMFVetClient.app  →  .dmg   (AppleScript'SİZ)
# -----------------------------------------------------------------------------
# NEDEN AYRI BETİK: `tauri build`in kendi dmg adımı (bundle_dmg.sh) pencereyi
# süslemek için Finder'ı AppleScript ile sürüyor. GUI oturumu olmayan her yerde
# (SSH, CI, macos-14 runner) bu adım DÜŞER ve .dmg üretilmez — .app üretilmiş
# olsa bile. hdiutil ile üretmek standart, headless ve tekrarlanabilir.
#
# Kullanım:
#   npx @tauri-apps/cli build --bundles app     # önce .app üret
#   ./build_dmg.sh
#
# İmzalama (opsiyonel, Developer ID keychain'de ise):
#   PEMF_CODESIGN_ID="Developer ID Application: ... (TEAMID)" ./build_dmg.sh
# =============================================================================
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

APP_NAME="PEMFVetClient"
VERSION="$(sed -n 's/^version *= *"\(.*\)"/\1/p' Cargo.toml | head -1)"
ARCH="$(uname -m)"                     # arm64 | x86_64
APP="target/release/bundle/macos/${APP_NAME}.app"
OUT="target/release/bundle/dmg/${APP_NAME}_${VERSION}_${ARCH}.dmg"

[[ -d "$APP" ]] || { echo "[HATA] $APP yok. Önce: npx @tauri-apps/cli build --bundles app" >&2; exit 1; }

# tauri'nin yarım bıraktığı okuma-yazma DMG'leri temizle (rw.*.dmg) — kalırlarsa
# hangi dosyanın yayınlanacağı karışır.
rm -f target/release/bundle/macos/rw.*.dmg target/release/bundle/dmg/rw.*.dmg "$OUT"
mkdir -p "$(dirname "$OUT")"

# --- İmzalama (notarization'ın ÖN KOŞULU) -----------------------------------
if [[ -n "${PEMF_CODESIGN_ID:-}" ]]; then
  echo "==> İmzalanıyor: $PEMF_CODESIGN_ID"
  codesign --force --deep --timestamp --options runtime --sign "$PEMF_CODESIGN_ID" "$APP"
  codesign --verify --deep --strict "$APP"
  echo "    [OK] imza doğrulandı"
else
  echo "==> PEMF_CODESIGN_ID yok → imzasız (.dmg sağ tık → Aç ile açılır)"
fi

# --- Sahne: .app + /Applications kısayolu ------------------------------------
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"   # sürükle-bırak kurulumu

echo "==> DMG üretiliyor: $OUT"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$STAGE" \
  -fs HFS+ \
  -format UDZO \
  -ov \
  "$OUT" >/dev/null

# --- DMG'nin KENDİSİNİ de imzala ---------------------------------------------
# .app imzalı olsa bile kapsayıcı imzasızsa indirilen dosya "bilinmeyen geliştirici"
# uyarısı alabilir; Apple da notarization için imzalı kapsayıcı bekler.
if [[ -n "${PEMF_CODESIGN_ID:-}" ]]; then
  codesign --force --timestamp --sign "$PEMF_CODESIGN_ID" "$OUT"
  codesign --verify --strict "$OUT" && echo "    [OK] DMG imzası doğrulandı"
fi

# --- Doğrula ------------------------------------------------------------------
hdiutil verify "$OUT" >/dev/null && echo "    [OK] DMG bütünlüğü doğrulandı"
shasum -a 256 "$OUT" | tee "${OUT}.sha256.txt"
printf '\n\033[1;32m✓ %s\033[0m (%s)\n' "$OUT" "$(du -h "$OUT" | cut -f1)"

if [[ -z "${PEMF_CODESIGN_ID:-}" ]]; then
  cat <<'EOF'

NOT: İmzasız DMG. Notarization için sırayla:
  1. PEMF_CODESIGN_ID ile yeniden üret (Developer ID Application sertifikası)
  2. xcrun notarytool submit <dmg> --apple-id <id> --team-id <team> --password <app-password> --wait
  3. xcrun stapler staple <dmg>
EOF
fi
