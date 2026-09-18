// Jest global setup (audit B-3.2). AsyncStorage native modülü resmî jest mock'u ile değiştirilir
// (config.ts token/device-id saklama testleri için). fetch her testte mock'lanır.
jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock")
);

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
