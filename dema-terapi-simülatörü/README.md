# DEMA Terapi Simülatörü — tanıtım / eğitim aracı

Düşük Enerjili Manyetik Alan (DEMA) terapi parametrelerini (frekans, yoğunluk, dalga biçimi, süre) ayarlayıp biyolojik
etkileri canlandıran tek sayfalık bir React + Vite uygulaması. **Tanıtım/eğitim amaçlıdır, cihaz davranışını temsil
etmez** (sahip kararı A-37): cihaza bağlanmaz, bobin sürmez, ölçüm göstermez. Dayanaksız uyumluluk iddiası ve fiziksel
modeli olmayan alan göstergesi D1.91'de kaldırıldı. Dizin CANLI — silinmez (D5.36 kapısı:
[`tests/test_silinecek_sanilan_dizinler_CANLI.py`](../tests/test_silinecek_sanilan_dizinler_CANLI.py)).

> Bu dosya eskiden Google AI Studio şablonunun İngilizce README'siydi (yerelde çalıştırma + Gemini API anahtarı
> talimatı). Simülatörün kaynağı Gemini'yi ÇAĞIRMAZ (`src/` içinde `@google/genai` / `GEMINI_API_KEY` kullanımı yok);
> `package.json`daki `@google/genai` bağımlılığı ve `vite.config.ts`deki `GEMINI_API_KEY` tanımı şablondan kalmadır —
> çalıştırmak için anahtar GEREKMEZ.

## Üründe nerede

- **Derleme:** kurulum paketi hazırlanırken [`build_tools/build_installer.ps1`](../build_tools/build_installer.ps1) "Adım 4.6"
  bu dizinde `npm ci` → `npm run lint` (tip denetimi) → `npm run build` koşar; çıktı `dist/` (depoda TAKİPSİZ, `.gitignore`).
- **Paketleme:** [`build_tools/PEMF_Backend_onedir.spec`](../build_tools/PEMF_Backend_onedir.spec) `dist/`i gömmeden önce
  [`build_tools/dema_iddia_denetimi.py`](../build_tools/dema_iddia_denetimi.py) ile denetler; A-37 ile çelişen bayat bir
  `dist` derlemeyi DURDURUR (yeniden `npm run build`).
- **Sunum:** backend `dist/`i `/simulator` yolundan sunar (`apps/backend/servers/api_server.py`, "DEMA Simülatörü host etme");
  arayüzün DEMA ekranı (`apps/ui/src/screens/DemaSimulatorScreen.tsx`) onu `/simulator/index.html?dil=…` ile çerçevede açar.

## Dil

Metinler `src/i18n/tr.json` ve `src/i18n/en.json`'da (i18next YOK; `src/i18n/index.ts`). Sayfa dili `?dil=tr|en`, yoksa
tarayıcı dili; İngilizce bayrağı (`src/i18n/bayrak.ts`) kapalıyken her durumda Türkçe. Yeni metin iki dilde eklenir.

## Geliştirme

Önkoşul: Node.js.

```bash
npm install
npm run dev      # Vite geliştirme sunucusu (:3000)
npm run lint     # tsc --noEmit
npm run build    # dist/ — ürüne giren çıktı
```

## Kapılar

- [`tests/test_D191_dema_simulator_A37_tanitim_etiketi_iddiasiz.py`](../tests/test_D191_dema_simulator_A37_tanitim_etiketi_iddiasiz.py) — etiket ve iddiasız kaynak; bayat `dist` derlemeyi durdurur.
- [`tests/test_i18n_dema_altyapi.py`](../tests/test_i18n_dema_altyapi.py), [`tests/test_dema_iletileri_P1.py`](../tests/test_dema_iletileri_P1.py) — dil altyapısı ve katalog.
- [`tests/test_dema_README_GERCEGI_anlatir_L1_7_7.py`](../tests/test_dema_README_GERCEGI_anlatir_L1_7_7.py) — bu belge.
