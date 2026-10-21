// Jest global setup (audit B-3.2). AsyncStorage native modülü resmî jest mock'u ile değiştirilir
// (config.ts token/device-id saklama testleri için). fetch her testte mock'lanır.
jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock")
);

// I18N-0 (T13): i18n TR + SENKRON başlar → mevcut Türkçe metin / rol sorguları DEĞİŞMEDEN geçer. KATI kip: katalogda olmayan anahtar
// `t()` içinde HATA atar (ekrana anahtarı basıp sorguyu sessizce geçirmez). EN'i deneyen test `__bayrakTestiAyarla(true)` +
// `i18n.changeLanguage("en")` kullanır ve sonunda geri alır (bkz. `src/i18n/__tests__/altyapi.test.tsx`).
(globalThis as { __PEMF_I18N_KATI__?: boolean }).__PEMF_I18N_KATI__ = true;
// I18NI (14-I18N-INCELEME): İngilizce bayrağı AÇIK → başlangıç dili kayıtlı seçim, yoksa CİHAZ YERELİ (`Intl`). Testin dili koşum
// makinesinin yereline bağlı OLMASIN (bu makine tr-TR, CI `ubuntu-latest` genelde en-US → tüm Türkçe sorgular kırmızı olurdu): cihaz yereli
// testlerde tr-TR'ye sabitlenir; yerel → dil kuralı `etkinDil(…, yerel)` ile birim testlerinde ayrıca ölçülür.
jest.mock("@/i18n/dil", () => ({ ...jest.requireActual("@/i18n/dil"), cihazYereli: () => "tr-TR" }));
require("@/i18n");

// audit B-10.2: expo-secure-store native modülü → test'te AsyncStorage-mock'una delege (in-memory;
// AsyncStorage.clear() ikisini de temizler; token round-trip testleri değişmeden çalışır).
jest.mock("expo-secure-store", () => {
  const mod = require("@react-native-async-storage/async-storage");
  const AS = mod.default || mod;
  return {
    setItemAsync: (k: string, v: string) => AS.setItem("secure:" + k, v),
    getItemAsync: (k: string) => AS.getItem("secure:" + k),
    deleteItemAsync: (k: string) => AS.removeItem("secure:" + k),
  };
});

// [S5, 2026-09-04] SafeAreaProvider VARSAYILAN mock'u. Üretimde sağlayıcı `app/_layout.tsx`te
// köktedir; testler ise bileşenleri sağlayıcısız render ediyor ve `useSafeAreaInsets()`
// "No safe area value available" diye ATIYOR. Güvenli alanı okuyan bileşen sayısı arttıkça
// (kabuk, ACİL DURDUR, Toast, açılış kapısı, modallar) her test dosyasına aynı mock kopyalanır
// hâle gelmişti — tek yerden sıfır inset veriliyor.
// ⚠️ Çentik/inset DAVRANIŞINI ölçen testler kendi `jest.mock`'unu yazar; dosya bazlı mock BUNU EZER.
jest.mock("react-native-safe-area-context", () => {
  const gercek = jest.requireActual("react-native-safe-area-context");
  return {
    ...gercek,
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
  };
});
