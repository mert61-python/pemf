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
