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
 * D1.E02 · A-51 (sahip, 2026-10-01): gizleme artık ROTA ADINA DEĞİL, ekranın GERÇEKTEN kendi durdurma düğmesini
 * çizmesine bağlı (`KendiDurdurmaIsareti`). Eski "küme sessizce büyümesin" pini davranışsal kapıya devredildi:
 * `AppShell.D1E02.gorunurDurdurma.test.tsx` her rotayı boş içerikle çizer ve kayan kutuyu arar.
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
