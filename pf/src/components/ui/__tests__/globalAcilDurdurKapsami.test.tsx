// Author: mertaygn
/**
 * KAYAN ACİL DURDUR — KAPSAM KAPISI (sahip bildirimi 2026-09-12).
 * ==============================================================
 * "seans başlatınca şu sol altta çıkan acil durdurma kutusunu kaldır zaten bir sürü var
 *  uygulama içinde."
 *
 * Sahip HAKLIYDI: Kontrol ekranında aynı anda ÜÇ durdurma görünüyordu (seans kartı ·
 * "TÜM BOBİNLERİ ACİL DURDUR" · kayan kutu).
 *
 * ═══════════════════════════════════════════════════════════════════════════════
 * ⚠️ AMA KALDIRMA HER YERE UYGULANAMAZ — BU DOSYANIN ASIL İŞİ BUDUR
 * ═══════════════════════════════════════════════════════════════════════════════
 * Bu düğme, uygulamanın 10 rotasının 8'inde TEK durdurma kontrolüdür (Akıllı Teşhis,
 * Ayarlar, Tedavi Geçmişi, Hastalar, Raporlar, Sensörler, AI Geçmişi, Simülasyon) ve
 * OTONOM SÜRÜŞ tam da Akıllı Teşhis'ten başlatılabiliyor. Oralarda gizlemek, fazlalığı
 * değil ERİŞİMİ kaldırmak olurdu — bileşenin var olma sebebinin tersi.
 *
 * Bu yüzden gizleme ROTA BAZLIDIR ve küme bilerek kısadır. Kapı, kümenin sessizce
 * büyümesini engeller.
 */
import { render } from "@testing-library/react-native";
import { GlobalEmergencyStop } from "@/components/ui/GlobalEmergencyStop";

const KOSAN = {
  gateway: "online",
  mqtt: "online",
  stm: "online",
  coils: [{ id: 1, running: true, connected: true }],
  activeTreatment: { isActive: true },
  notifications: [],
};

jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: KOSAN }),
}));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/services/apiClient", () => ({ platformAlert: jest.fn() }));
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(),
  EMERGENCY_STOP_UNCONFIRMED_TITLE: "t",
  EMERGENCY_STOP_UNCONFIRMED_BODY: "b",
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));

test("KRITIK: KENDI dugmesi olan ekranda kayan kutu GIZLENIR", () => {
  // Sahibin isteği: Kontrol/Ana Ekran'da üç düğme yerine tek düğme.
  //
  // MUTASYON: `if (gizle) return null;` satırını sil → KIRMIZI.
  const api = render(<GlobalEmergencyStop gizle />);
  expect(api.toJSON()).toBeNull();
});

test("KRITIK: KENDI dugmesi OLMAYAN ekranda kayan kutu GORUNUR (donanim kosarken)", () => {
  // ⚠️ ASIL GÜVENLİK DEĞİŞMEZİ: 8 rotada bu TEK durdurma kontrolüdür ve otonom sürüş
  // Akıllı Teşhis'ten başlatılabiliyor. Buranın gizlenmesi, fazlalık temizliği değil
  // erişim kaybıdır.
  //
  // MUTASYON: `gizle` varsayılanını `true` yap → KIRMIZI.
  const api = render(<GlobalEmergencyStop />);
  expect(api.toJSON()).not.toBeNull();
});

test("KRITIK: gizleme KUMESI sessizce BUYUMESIN (yalniz kendi dugmesi olan iki rota)", () => {
  // ⚠️ Küme `AppShell`te tanımlı ve bir satır eklemek 8 rotanın birinde durdurmayı
  // sessizce kaldırabilir. Kapı, KAYNAĞA pinli sabit bir liste ölçer.
  //
  // MUTASYON: kümeye "ai" ekle → KIRMIZI (Akıllı Teşhis'te durdurma kaybolurdu).
  /* eslint-disable @typescript-eslint/no-require-imports */
  const fs = require("fs");
  const path = require("path");
  /* eslint-enable @typescript-eslint/no-require-imports */
  const src = fs.readFileSync(
    path.join(__dirname, "..", "AppShell.tsx"),
    "utf-8",
  ) as string;
  const m = src.match(/KENDI_DURDURMASI_OLAN_ROTALAR[^=]*=\s*new Set<RouteKey>\(\[([^\]]*)\]\)/);
  expect(m).toBeTruthy();
  const rotalar = (m![1].match(/"([a-z_]+)"/g) ?? []).map((x) => x.replace(/"/g, ""));
  expect(rotalar.sort()).toEqual(["control", "dashboard"]);
});
