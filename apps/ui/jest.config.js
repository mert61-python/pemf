// Frontend test yapılandırması (audit B-3.2: sıfır test → Jest + jest-expo).
// Servis/mantık testleri (apiClient, config, wsClient) için jest-expo preset (RN transform)
// + AsyncStorage mock + '@/' path alias. Component render testleri (RNTL) ayrı bir aşama.
module.exports = {
  preset: "jest-expo",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  testMatch: ["**/__tests__/**/*.test.ts", "**/__tests__/**/*.test.tsx"],
  // ⚠️ TEST BASINA ZAMAN ASIMI — varsayilan 5000 ms SOGUK CI'da YETMIYOR (2026-09-15, kosu
  // 34998091761). `AiProPanelArastirma` dosyasinin ILK testi CI'da "Exceeded timeout of
  // 5000 ms" ile dustu; AYNI test yerelde 273 ms suruyor (olculdu, jest --json). 18 katlik
  // fark runner'in yavasligi DEGIL:
  //   · CI npm'i onbellege aliyor (`cache: npm`) ama JEST TRANSFORM onbellegini ALMIYOR,
  //   · expo `fetch` global'i TEMBEL bir getter (expo/src/winter/installGlobal.ts:44) ve ilk
  //     dokunusta expo-modules-core -> ExpoFetchModule -> fetch zincirini require ediyor.
  // Yani sure test MANTIGINDA degil, ILK DOKUNUSTAKI babel transform'unda harcaniyor ve
  // faturayi o an hangi test kosuyorsa o oduyor — yani suclu test RASTGELE degisir.
  //
  // ⚠️ NEDEN "kararsiz test" deyip gecilmedi: hata mesaji zaman asimi, iddia hatasi degildi;
  // yerel sure olculdu (16 test toplam 795 ms) ve CI log'unda expo require zinciri goruldu.
  // ⚠️ NEDEN 20 sn: gercek is 795 ms — 25 kat pay. Bu tavan bir SONSUZ BEKLEMEYI hala
  // yakalar (fake-timer ile asilan bir promise 20 sn'de de bitmez), yalniz soguk transform
  // penceresini kapatir. Yukseltmeyin; yukseltmek gerekiyorsa once NEDEN yavasladigini olcun.
  // Kapi: tests/test_jest_zaman_asimi_kapisi.py
  testTimeout: 20000,
  transformIgnorePatterns: [
    "node_modules/(?!((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules|sentry-expo|native-base|react-native-svg|@react-native-async-storage/.*|lucide-react-native))",
  ],
  // Y243 (KP-2 A5): kapsam paydası (KP-1'de genişletildi: ürün kaynağının tamamı, 166 dosya; araç yapılandırmaları
  // eslint / jest / metro / jest.setup payda DIŞI) + eşik — CI `npm test -- --coverage` ile uygulanır. Eşikler ölçülenin
  // ~1 puan altı; yalnız YÜKSELTİLİR. KP-2 kapanış (2026-11-03) ölçülen: satır %89,01 · deyim %84,94 · dal %79,60 · fonksiyon %81,28.
  // KP-3 AŞAMA D (2026-11-08, uç 6c7d4f10) ölçülen: satır %98,27 (8 049 / 8 190) · deyim %96,40 · dal %88,78 · fonksiyon %93,52.
  // KP-4 C (2026-11-11, B1 + B3 sonrası arayüz içeriği, 449 süit) ölçülen: satır %99,40 (8 293 / 8 343) · deyim %97,45 · dal %89,54 ·
  // fonksiyon %95,81 → 98 / 96 / 88 / 94. Kalan satırlar ULAŞILAMAZ savunmalar + 1 ZAMAN (KAPSAM.md KP-4 · B1).
  // KP-5 F (2026-11-15, uç 97b8d61e, 471 süit) ölçülen: satır %100 (8 547 / 8 547) · deyim %98,21 · dal %90,08 · fonksiyon %97,04
  // → 99 / 97 / 89 / 96. Erişilemez satırlar gerekçeli `istanbul ignore` + sayan kapı (Y279, test_KP5_istemci_site_etiketleri_SAYILI).
  collectCoverageFrom: [
    "src/**/*.{ts,tsx,js,jsx}",
    "app/**/*.{ts,tsx,js,jsx}",
    "modules/**/*.{ts,tsx,js,jsx}",
    "auth-pages/**/*.{js,jsx,ts,tsx}",
    "scripts/**/*.{js,jsx,ts,tsx,mjs,cjs}",
    "!**/__tests__/**",
    "!**/*.d.ts",
    "!**/node_modules/**",
  ],
  coverageThreshold: {
    global: { lines: 99, statements: 97, branches: 89, functions: 96 },
  },
};
