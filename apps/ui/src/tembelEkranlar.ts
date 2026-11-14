// Author: mertaygn, cglrgrkn
/* istanbul ignore file -- PLATFORM: `import()` jest'te KOŞMAZ (dinamik içe aktarma dönüştürücüsü yok; yeni bağımlılık YOK — Y279); PemfApp testleri tembel yüklemeyi sahteler */
/**
 * PemfApp'in TEMBEL yüklenen ekranları (audit B-6.1: code-splitting — ilk boyama Welcome / Dashboard EAGER; ağır / nadir ekranlar
 * LAZY → açılış paketi küçülür, özellikle web tek paket). Named export → default'a sarılır; Suspense yedeği PemfApp'te.
 *
 * KP-5 (sahip Y279, 12-11): `import()` gövdeleri bu KÜÇÜK modüle ayrıldı — PemfApp yalnız `lazy(tembelEkranlar.X)` bağlar. Jest
 * `import()`u çalıştıramaz; gövdeler gerekçeli etiketle (yukarıda, sayan kapı `tests/test_KP5_istemci_site_etiketleri_SAYILI.py`)
 * ölçümden çıkar; modül / ad eşlemesi testte fabrikanın kendi metninden okunur (KP3-PemfApp-yonlendirici). Davranış AYNI.
 */
export const tembelEkranlar = {
  ControlScreen: () => import("@/screens/ControlScreen").then((m) => ({ default: m.ControlScreen })),
  DemaSimulatorScreen: () => import("@/screens/DemaSimulatorScreen").then((m) => ({ default: m.DemaSimulatorScreen })),
  KpiDashboardScreen: () => import("@/screens/KpiDashboardScreen").then((m) => ({ default: m.KpiDashboardScreen })),
  SensorMonitorScreen: () => import("@/screens/SensorMonitorScreen").then((m) => ({ default: m.SensorMonitorScreen })),
  TreatmentHistoryScreen: () => import("@/screens/TreatmentHistoryScreen").then((m) => ({ default: m.TreatmentHistoryScreen })),
  PatientScreen: () => import("@/screens/PatientScreen").then((m) => ({ default: m.PatientScreen })),
  AiHubScreen: () => import("@/screens/AiHubScreen").then((m) => ({ default: m.AiHubScreen })),
  SettingsScreen: () => import("@/screens/SettingsScreen").then((m) => ({ default: m.SettingsScreen })),
  AiHistoryScreen: () => import("@/screens/AiHistoryScreen").then((m) => ({ default: m.AiHistoryScreen })),
};
