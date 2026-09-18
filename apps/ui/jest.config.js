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
};
