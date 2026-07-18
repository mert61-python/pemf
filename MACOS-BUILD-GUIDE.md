# macOS Client — GitHub Actions ile İmzalı+Notarized .dmg (fiziksel Mac olmadan)

Apple Developer hesabın var → GitHub Actions'ın `macos` runner'ı Apple'ın Mac'inde build + imza +
notarization yapar. Sen bu makineden tetikle, imzalı `.dmg`'yi artifact olarak indir.

## 0) Ön koşul
- Apple Developer Program üyeliği (aktif). Team ID: **developer.apple.com → Membership → Team ID** (10 karakter).

## 1) "Developer ID Application" sertifikası — Mac OLMADAN (Windows'ta openssl)
> openssl WSL'de veya Git Bash'te var. `<...>` yerlerini doldur.

```bash
# a) Özel anahtar + CSR üret
openssl genrsa -out devid.key 2048
openssl req -new -key devid.key -out devid.csr -subj "/emailAddress=<apple-id-email>/CN=<Adin Soyadin>/C=TR"
```
- b) **developer.apple.com → Certificates → +** → **"Developer ID Application"** seç → `devid.csr`'i yükle → oluşan **`developerID_application.cer`**'i indir.
- c) .cer + key → .p12 (şifreli):
```bash
openssl x509 -in developerID_application.cer -inform DER -out devid.pem -outform PEM
openssl pkcs12 -export -out devid.p12 -inkey devid.key -in devid.pem -passout pass:<P12_SIFRE>
# GitHub secret için base64 (tek satır):
base64 -w0 devid.p12 > devid.p12.b64     # (Git Bash'te: base64 devid.p12 | tr -d '\n')
```
- d) İmza kimliğini öğren (sertifikanın CN'i): genelde `Developer ID Application: <Adin> (<TEAMID>)`.

## 2) App-specific password (notarization için)
**appleid.apple.com → Oturum Aç ve Güvenlik → Uygulamaya Özel Parolalar → +** → üret (ör. `abcd-efgh-ijkl-mnop`).

## 3) GitHub repo + secret'lar
1. Client kaynağı için **private** GitHub repo aç, `pemf-vet-client/` içeriğini push et.
   ```bash
   cd pemf-vet-client
   git init && git add . && git commit -m "client"
   gh repo create pemf-vet-client --private --source=. --push   # ya da elle
   ```
2. **Repo Settings → Secrets and variables → Actions → New repository secret** ile şunları ekle:

| Secret | Değer |
|---|---|
| `APPLE_CERTIFICATE` | `devid.p12.b64` içeriği (base64) |
| `APPLE_CERTIFICATE_PASSWORD` | `<P12_SIFRE>` |
| `APPLE_SIGNING_IDENTITY` | `Developer ID Application: <Adin> (<TEAMID>)` |
| `APPLE_ID` | Apple ID e-postan |
| `APPLE_PASSWORD` | app-specific password (adım 2) |
| `APPLE_TEAM_ID` | 10 karakterli Team ID |

## 4) Çalıştır
Repo → **Actions → "macOS Client" → Run workflow**. Bitince **Artifacts → PEMF-Vet-Client-macOS** → `.dmg` indir.
(Workflow: `.github/workflows/macos-release.yml` — universal Intel+ARM, imzalı+notarized.)

## 5) Dağıt
`.dmg`'yi `pemf-update` release'ine yükle (veya bir host'a) → web `config.ts`:
`macosReady: true` + `macosAsset` = .dmg URL.

---
### Notlar
- `src-tauri/tauri.conf.json` içinde geçerli bir **`identifier`** (bundle ID, ör. `com.vpemf.vetclient`) olmalı — imza için şart. (Build'den önce kontrol edeceğiz.)
- İmzalı+notarized `.dmg` → macOS'ta **uyarısız** açılır. (İmzasız istersen bu adımları atla; kullanıcı sağ-tık→Aç yapar.)
- Maliyet: private repo'da ~200 ücretsiz macOS-dk/ay (build ~15dk → ayda ~10 build ücretsiz).
