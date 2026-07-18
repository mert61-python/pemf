# PEMF Vet — Production Auth & Entitlement Planı

> Şu an **test fazı**: açık-erişim (login yok, tüm profiller ücretsiz). Bu doküman, **ödeme/production'a**
> geçerken uygulanacak endüstri-standardı auth + lisans (entitlement) mimarisini tanımlar.
> Karar: mimari şimdi netleştirildi, **uygulama ödeme başlayınca** yapılacak.

---

## 1. Mevcut durum (test)

| Katman | Durum | Bayrak |
|---|---|---|
| Client login | **Atlanıyor** (herkes kurar) | `FREE_MODE = true` (src/config.ts) |
| Uygulama (localhost:8000) | Açık-erişim | app tarafı entitlement `ENFORCED=false` |
| Model indirme | **Kimliksiz** — GitHub release URL'leri public | — (kapı yok) |
| Backend tier | Zorlanmıyor | `PEMF_TIER_ENFORCED` unset |

**Sorun:** GB'lık özel AI modelleri kimlik/yetki olmadan indirilebiliyor (fikri mülkiyet + bant genişliği).

---

## 2. Hedef mimari (production) — "client = uygulama kabuğu"

```
[Public installer indir]  ✅ normal (Slack/Zoom/Docker gibi — kapı burada DEĞİL)
        │
        ▼
[Client açılır → LOGIN]  (tek Supabase hesabı, client kendi penceresinde)
        │  access_token + entitlement
        ▼
[Entitlement → yalnız yetkili profillerin modelleri iner]  (imzalı, kısa-ömürlü URL)
        │
        ▼
[Uygulama client'in KENDİ native penceresinde açılır]  ✅ (v1.3.3 ile YAPILDI)
        │  session token enjekte edilir → app OTOMATİK giriş (çift-login yok = SSO)
        ▼
[Backend yerel servis: donanım + AI]   (tier bayrağı ile sınırlar)
```

**Tek hesap, tek giriş (SSO).** Client bir kez login → token hem indirmeyi yetkilendirir hem app'e aktarılır.

---

## 3. Çevrilecek bayraklar

| Yer | Bayrak | test → production |
|---|---|---|
| `pemf-vet-client/src/config.ts` | `FREE_MODE` | `true → false` (Login ekranı + entitlement gating aktif) |
| App (pf) | `ENTITLEMENT_ENFORCED` | `false → true` |
| Backend | `PEMF_TIER_ENFORCED` | unset → `1` |

Parçaların çoğu **zaten var**: client `Login.tsx` + `lib/entitlement.ts`, app `AuthScreen` + `EntitlementContext`, backend tier mantığı.

---

## 4. Model indirmesini koruma (asıl eksik)

Bugün model URL'leri public GitHub release. Public URL **auth-gate edilemez**. Production seçenekleri:

**A) İmzalı, kısa-ömürlü URL (önerilen).**
- Modeller özel depoya taşınır (Supabase Storage / Cloudflare R2 / S3).
- Bir **Edge Function / sunucu ucu**: `POST /entitled-manifest` — geçerli Supabase session + entitlement doğrular → yalnız yetkili profillerin modelleri için **imzalı, ~10 dk geçerli** indirme URL'leri döner.
- Client: login → bu ucu çağırır → dönen imzalı URL'lerden indirir (mevcut resumable `download_to` + sha256 aynen kullanılır).
- Manifest'e `sha256` zaten var (bütünlük) → sadece URL üretimi auth-gate'lenir.

**B) (Zayıf) public URL + client-içi gating** — URL'ler bilinirse bypass edilir; IP korunmaz. Kullanma.

> Not: SmartScreen "bilinmeyen yayıncı" uyarısı için **ücretli kod-imzalama** gerekir (ayrı konu; güncelleme zaten sha256-korumalı).

---

## 5. SSO — client oturumunu app'e aktarma (çift-login yok)

Client Supabase ile login → session var. App (localhost:8000) ayrı origin. Aktarım:

- **En temiz:** Tauri app-penceresi oluşturulurken **init-script** ile app'in Supabase oturumunu localStorage'a yaz:
  `WebviewWindowBuilder…initialization_script("localStorage.setItem('sb-<proj>-auth-token', '<session_json>')")`
  → app'in Supabase client'ı oturumu görür → **otomatik giriş**.
- Alternatif: tek-kullanımlık kod (`?code=…`) → app açılışta `exchange` eder (URL'de ham token taşımaz).

`open_app_window` (lib.rs) buna göre `url` + opsiyonel session parametresi alacak şekilde genişletilir.

---

## 6. Uygulama sırası (production'a geçerken)

1. **Modelleri özel depoya taşı** + entitled-manifest Edge Function (auth + imzalı URL).
2. Client: `FREE_MODE=false` → Login zorunlu; indirme entitled-manifest'ten.
3. SSO: `open_app_window`'a init-script ile session enjeksiyonu (çift-login yok).
4. App: `ENTITLEMENT_ENFORCED=true`; Backend: `PEMF_TIER_ENFORCED=1`.
5. iyzico/ödeme → entitlement kaynağı (abonelik → profiller/tier).
6. (Ops.) Ücretli kod-imzalama → SmartScreen uyarısı kalkar.

---

## 7. Değişmeyecekler (zaten doğru)

- ✅ Public installer indirme (endüstri standardı).
- ✅ Uygulama native pencerede (v1.3.3).
- ✅ Yerel backend servisi (donanım/AI) + resumable indirme + sha256 bütünlük.
- ✅ Hash-korumalı self-update.
