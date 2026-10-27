// Author: mertaygn, cglrgrkn
/**
 * D5.E2 (İG-6.30 · K-3 · D5 3. dalga) — A-51 değişmezi: ekranın `KendiDurdurmaIsareti` TAKILIYSA (kayan ACİL DURDUR gizli) o ekran
 * KENDİ ACİL DURDUR'unu ÇİZER ve basınca durdurma GERÇEKTEN gider. Her işaret takan ekran (Ana Ekran + Kontrol) × {STM bağlı, kopuk}
 * × {seans aktif, seanssız bobin çalışıyor, boşta}.
 * ======================================================================================================================
 * ÖLÇÜLEN KÖRLÜK (HEAD d38b0db5, çürütme r2): Kontrol ekranının kendi düğmesi `isStmConnected ? (…) : null` koşuluna girer,
 * `<KendiDurdurmaIsareti />` koşulsuz kalırsa STM kopukken ekranda durdurma kontrolü SIFIR (işaret takılı → kayan düğme gizli, ekranın
 * düğmesi yok) — 55 ilgili jest dosyası (1203 test) YEŞİL kaldı: D1E02 Kontrol rotası için `Patlayan` kullanır, `ControlScreen.*`
 * testleri hep `stm: "online"` koşar. Aynı aile k630d (Ana Ekran işareti düğmenin ÇİZİLMEDİĞİ dala takılır) yalnız D1E02 (B) ile
 * yakalanıyordu. Bu kapı değişmezi TABLO olarak ölçer (planın "rota × çalışıyor/boşta" FARKLI yönteminin işaret takan ekranlara
 * indirgenmişi).
 *
 * GERÇEK: `useKendiDurdurmaKaydi` (AppShell'in kullandığı kayıt), `KendiDurdurmaIsareti`, `DashboardScreen`, `ControlScreen`,
 * `PatientGate`, `SessionProgressCard`, `useSessionControl`, `performEmergencyStop`, `apiClient`. Sahte EN ALT katta: `global.fetch`
 * (kaydedici; `/session/active` tabloya göre) + bağlamlar (canlı veri, kimlik, gezinme) + ilgisiz ağır paneller.
 * ⚠️ Yalnız KAPI: ACİL DURDUR / STOP davranışı değişmez; bu dosya ürün koduna dokunmaz. "Kendi düğme" = ekranın içinde erişim
 * etiketi /acil durdur/i olan ve basınca `/hardware/emergency_stop` gönderen kontrol (görünür ama ölü düğme SAYILMAZ).
 *
 * ⚠️ MUTASYON: Kontrol düğmesi STM koşuluna girer, işaret koşulsuz (r2) → "control × offline × boşta" KIRMIZI; Ana Ekran işareti
 * düğmesiz dala (k630d) → "dashboard × boşta" KIRMIZI; Ana Ekran düğmesi STM koşuluna girer → "dashboard × offline × seans" KIRMIZI;
 * Kontrol düğmesi STM kopukken `disabled` ya da `onPress` boş → "control × … × boşta" KIRMIZI (çizili ama basılamaz).
 */
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api", bridgeBaseUrl: "http://127.0.0.1:8000/api", apiToken: "" },
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("@/services/deviceRegistry", () => ({ getRemoteUrlForDevice: jest.fn(async () => null) }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
let mockSnap: Record<string, unknown>;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockSnap, wsConnected: true, connectionQuality: "live", haveRealData: true,
    telemetryStale: false, sensorHistory: {}, unreadCount: 0, markAllRead: jest.fn(),
    clearNotifications: jest.fn(), refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
    donanimBelirsiz: false,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ userMode: "veterinarian", setUserMode: jest.fn(), isExpert: true, isResearcher: false }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" }, logout: jest.fn() }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperator: () => ({ operator: "Dr. X" }),
  useOperatorOptional: () => null,
}));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({
    navigate: jest.fn(), goTo: jest.fn(), navigateTo: jest.fn(),
    selectedPatient: { id: "1", name: "Boncuk" }, setSelectedPatient: jest.fn(),
  }),
}));
jest.mock("@/components/ui/NotificationCenter", () => ({ NotificationCenter: () => null }));
jest.mock("@/components/domain/AiProPanel", () => ({ AiProPanel: () => null }));
jest.mock("@/components/domain/EFieldBar", () => ({ EFieldBar: () => null }));
jest.mock("@/components/domain/ObservationNotesModal", () => ({ ObservationNotesModal: () => null }));
jest.mock("@/components/domain/CoilParameterPanel", () => ({ CoilParameterPanel: () => null }));

import { act, fireEvent, render } from "@testing-library/react-native";
import React from "react";
import { Alert, Text } from "react-native";
import { useKendiDurdurmaKaydi } from "@/components/ui/KendiDurdurmaKontrolu";
import { ControlScreen } from "@/screens/ControlScreen";
import { DashboardScreen } from "@/screens/DashboardScreen";

type Ekran = "dashboard" | "control";
type Stm = "online" | "offline";
type Durum = "seans_aktif" | "seanssiz_bobin_calisiyor" | "bosta";

const cagrilar: string[] = [];
let seansAktif = false;
const yanit = (o: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: async () => o, text: async () => JSON.stringify(o) });

const SEANS = { isActive: true, mode: "Manuel", frequencyHz: 50, intensityMt: 1, remainingMin: 29, elapsedSec: 10, durationSec: 1800 };
const HAZIR = { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 };

/** Tablonun bir satırının canlı durumu. STM kopukken bobin durumu BİLİNMEZ (backend `running:false`, `connected:false` bildirir). */
function kur(stm: Stm, durum: Durum) {
  seansAktif = durum === "seans_aktif";
  const calisan = stm === "online" ? (durum === "seans_aktif" ? [1, 2, 3, 4, 5, 6, 7] : durum === "seanssiz_bobin_calisiyor" ? [1] : []) : [];
  mockSnap = {
    gateway: "devre_disi", mqtt: "devre_disi", stm, internet: "offline",
    patient: null,
    activeTreatment: seansAktif ? SEANS : HAZIR,
    notifications: [],
    coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({
      id, running: calisan.includes(id), connected: stm === "online", stm32Driven: true,
      frequencyHz: calisan.includes(id) ? 50 : 0, dutyCycle: calisan.includes(id) ? 30 : 0,
      objectTemp: null, magneticMt: 0, currentA: 0, ambientTemp: null, measuredFields: [],
    })),
    system: {}, sessions: [],
  };
}

function Kabuk({ ekran }: { ekran: Ekran }) {
  const { takili, Saglayici } = useKendiDurdurmaKaydi();
  return (
    <>
      <Text testID="d5e2-isaret">{takili ? "takili" : "yok"}</Text>
      <Saglayici>{ekran === "dashboard" ? <DashboardScreen /> : <ControlScreen />}</Saglayici>
    </>
  );
}

const ETIKET = /acil durdur/i;

/** Bir satırı ölç: işaret takılı mı, ekranın kendi ACİL DURDUR'u kaç tane, kaçı basınca durdurma gönderiyor (ilk başarılıda durur). */
async function olc(ekran: Ekran, stm: Stm, durum: Durum) {
  kur(stm, durum);
  const u = render(<Kabuk ekran={ekran} />);
  await act(async () => {});
  const takili = u.getByTestId("d5e2-isaret").props.children === "takili";
  const dugme = u.queryAllByLabelText(ETIKET).length;
  let basilabilir = false;
  for (let i = 0; i < dugme && !basilabilir; i += 1) {
    const d = u.queryAllByLabelText(ETIKET)[i];
    if (!d) break;
    cagrilar.length = 0;
    await act(async () => {
      fireEvent.press(d);
    });
    await act(async () => {});
    basilabilir = cagrilar.includes("/hardware/emergency_stop");
  }
  u.unmount();
  return { ekran, stm, durum, takili, dugme, basilabilir };
}

beforeEach(() => {
  cagrilar.length = 0;
  seansAktif = false;
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  jest.spyOn(console, "error").mockImplementation(() => {});
  (global as { fetch: unknown }).fetch = jest.fn((url: string) => {
    const yol = String(url).replace("http://127.0.0.1:8000/api", "");
    cagrilar.push(yol);
    if (yol === "/session/active")
      return yanit(seansAktif ? { is_active: true, mode: "Manuel", frequency: 50, intensity: 1, duration_minutes: 30, elapsed_sec: 10 } : { is_active: false });
    if (yol === "/hardware/emergency_stop") return yanit({ confirmed: true, status: "success", stmStopped: true, stmKartYaniti: "kabul" });
    return yanit({ status: "success" });
  });
});
afterEach(() => jest.restoreAllMocks());

const EKRANLAR: Ekran[] = ["dashboard", "control"];
const STMLER: Stm[] = ["online", "offline"];
const DURUMLAR: Durum[] = ["seans_aktif", "seanssiz_bobin_calisiyor", "bosta"];
const TABLO = EKRANLAR.flatMap((e) => STMLER.flatMap((s) => DURUMLAR.map((d) => [e, s, d] as [Ekran, Stm, Durum])));

describe("D5.E2 (İG-6.30 · A-51) — işaret takılıysa ekranın KENDİ ACİL DURDUR'u çizili ve basılabilir", () => {
  it.each(TABLO)("KRİTİK: %s × STM %s × %s", async (ekran, stm, durum) => {
    const r = await olc(ekran, stm, durum);
    // İhlal: kayan ACİL DURDUR gizli (işaret takılı) ama ekranda basınca durduran kendi düğmesi YOK → durdurma kontrolü SIFIR (Ö.4-Y8).
    // Fark çıktısı satırın TAMAMINI gösterir (ekran / STM / durum / işaret / düğme sayısı / basılabilir).
    expect({ ...r, ihlal: r.takili && !r.basilabilir }).toEqual({ ...r, ihlal: false });
  });

  // GEÇİŞ (ikinci tur): ekran AÇIKKEN canlı durum değişir — düğme kaybolunca işaret de SÖKÜLMELİ (kayıt sayacı / effect temizliği).
  // Her satırı taze çizen tablo söküm yolunu ölçmez; burada aynı ağaç yeniden çizilir ve her adımda değişmez yeniden ölçülür.
  const GECIS: [Stm, Durum][] = [
    ["online", "seans_aktif"], ["offline", "bosta"], ["online", "seanssiz_bobin_calisiyor"], ["online", "bosta"],
    ["offline", "seans_aktif"], ["offline", "seanssiz_bobin_calisiyor"], ["online", "seans_aktif"], ["online", "bosta"],
  ];
  it.each(EKRANLAR)("KRİTİK geçiş: %s açıkken STM / seans durumu değişir — her adımda işaret takılıysa kendi düğme ÇİZİLİ", async (ekran) => {
    kur(...GECIS[0]);
    const u = render(<Kabuk ekran={ekran} />);
    await act(async () => {});
    const adimlar: { stm: Stm; durum: Durum; takili: boolean; dugme: number; ihlal: boolean }[] = [];
    for (const [stm, durum] of GECIS) {
      kur(stm, durum);
      u.rerender(<Kabuk ekran={ekran} />);
      await act(async () => {});
      const takili = u.getByTestId("d5e2-isaret").props.children === "takili";
      const dugme = u.queryAllByLabelText(ETIKET).length;
      adimlar.push({ stm, durum, takili, dugme, ihlal: takili && dugme === 0 });
    }
    u.unmount();
    expect(adimlar).toEqual(adimlar.map((a) => ({ ...a, ihlal: false })));
  });

  it("aparat / vakum: işaret GERÇEKTEN kayıt oluyor (Kontrol her durumda; Ana Ekran seans sırasında) — kapı boşa ölçmüyor", async () => {
    const kontrol = await olc("control", "offline", "bosta");
    const ana = await olc("dashboard", "offline", "seans_aktif");
    expect([kontrol, ana].map((r) => [r.ekran, r.takili, r.basilabilir])).toEqual([
      ["control", true, true],
      ["dashboard", true, true],
    ]);
  });
});
