# pf/ — Mobil + Web Uygulama Kaynağı (React Native / Expo) · **ANA KAYNAK**

Uygulamanın **tek yetkili kaynağıdır**. Buradan **iki** çıktı üretilir:
1. **Android APK / iOS IPA** (mobil uygulama),
2. **Web bundle** (`expo export --platform web` → `pf/dist`) — backend'in `localhost:8000/` kökünden servis ettiği React arayüz.

> `package.json` adı: **`pemf-responsive-frontend`**. Expo `~56`, React Native `^0.85.3`, React `19`, expo-router.
> Tek kod tabanı → **Web + Android + iOS**. Üç profil (Evcil Hayvan Sahibi · Veteriner · Araştırma) UI'yi role göre uyarlar.

> ⚠️ **Burayı düzenle — `../frontend/` değil.** `guii/frontend/` bu reponun **bayat 2. kopyasıdır**; yalnız onun `dist/`'i canlıdır (buradan aynalanır). Detay: [`../frontend/README.md`](../frontend/README.md).

---

## Dizin yapısı (`src/`)

| Yol | İçerik |
|---|---|
| `src/PemfApp.tsx` | Kök uygulama bileşeni |
| `src/screens/` | 12 ekran: Auth, Welcome, Dashboard, Control, Patient, SensorMonitor, TreatmentHistory, KpiDashboard, Settings, AiHub, AiHistory, DemaSimulator |
| `src/services/` | Backend/bulut istemcileri: `apiClient.ts`, `authApi.ts`, `supabaseAuth.ts`, `wsClient.ts`, `discovery.ts` (mDNS), `deviceRegistry.ts`, `installedProfiles.ts`, `therapyLimits.ts`, `updates.ts`, `config.ts` |
| `src/components/` | `ui/` · `domain/` · `visual/` + `UpgradeModal.tsx` |
| `src/context/` | React context'leri: AppNav · Auth · Entitlement · LiveData · UserMode *(tekil `context/`, `contexts/` değil)* |
| `src/hooks/`, `src/config/`, `src/theme/`, `src/types/`, `src/utils/` | Hook'lar, yapılandırma, tema (premium tasarım token'ları), tipler, yardımcılar |
| `app/` | expo-router girişi (`_layout.tsx`, `index.tsx`) |
| `android/` | **Tam native Android projesi** — APK build kökü (`build.gradle`, `gradlew`, `app/`) |
| `scripts/postexport-web.js` | `export:web` sonrası web bundle'ı backend'e uygun hale getirir |

## Komutlar (geliştirme)

```bash
npm install                 # bağımlılıklar (myenv/embedded ile ilgisi yok — bu Node tarafı)
npm run web                 # Expo web dev server (:3001)
npm run export:web          # web bundle üret → pf/dist  (postexport-web.js dahil)
npm run android / ios       # cihaz/emülatör
npm test / lint / typecheck # jest · eslint · tsc
```

## Build & yayın (özet — tam reçete [`../BUILD.md`](../BUILD.md))

| Çıktı | Nasıl | Sonuç |
|---|---|---|
| **APK** | `..\build_tools\build_apk.ps1` (guii kökünden) | `release_assets\PEMF_Vet_Mobil.apk` |
| **iOS IPA** | `npx eas build -p ios --profile production` (EAS bulut) | expo.dev → `.ipa` |
| **Web UI** | `npm run export:web` → `pf\dist` → `robocopy /MIR` ile `..\frontend\dist` + kurulu `_internal\frontend\dist` | Backend `/` kökünden servis eder |

## ⚠️ Dikkat

- **Sürüm:** `pf/app.json`'daki sürüm/`androidVersionCode` **elle değil** — kök [`../versions.json`](../versions.json) tek-kaynağından `build_tools/sync_versions.ps1` yazar. `androidVersionCode` her yayında artmalı (Play Store şartı, geri alınamaz).
- **`gradlew clean` YAPMA** → `react-native-async-storage` codegen bozulur. `build_apk.ps1` zaten clean yapmaz.
- **APK MAX_PATH:** guii derin bir yolda → ninja/CMake ANSI-260 sınırını aşar. `build_apk.ps1` kaynağı kısa köke (`C:\pb`) aynalayıp orada derleyerek çözer (`LongPathsEnabled` tek başına yetmez).
- **Web değişikliği** yalnız burada export edilir; `frontend/dist`'e aynalanmadıkça backend eski UI'yi sunar.

---
İlgili: [proje geneli](../README.md) · [mimari](../docs/ARCHITECTURE.md) · [build rehberi](../BUILD.md) · [frontend/ (canlı mirror)](../frontend/README.md)
