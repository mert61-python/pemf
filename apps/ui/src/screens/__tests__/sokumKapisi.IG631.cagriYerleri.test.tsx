// Author: mertaygn, cglrgrkn
/**
 * İG-6.31 — kabuğu söken iki ÇAĞRI YERİ hasta-güvenliği kapısına (useTeardownGuard) GERÇEKTEN bağlı mı?
 * ==================================================================================================
 * ÖLÇÜLEN KÖRLÜK (D5 doğrulaması, mutant GERÇEK bileşen ağacında, 129 ilgili jest dosyası): Ayarlar → "Farklı Bir Profile Geçiş
 * Yap" sarmalayıcısı (`if (await guardTeardown(...)) setUserMode(null)`) `setUserMode(null)`'a indirilince ya da Karşılama
 * ekranının "Çıkış yap"ı korumasız `logout()` yapılınca 1596/1596 YEŞİL kalıyordu — bobin çalışırken onaysız söküm (ACİL DURDUR'un
 * yaşadığı ağaç gider, operatör durdurma kontrolsüz kalır). Mevcut testler kapıyı ya hook düzeyinde (useTeardownGuard.*) ya da
 * ekranda SAHTE kapıyla (`useTeardownGuard: () => (f) => f`) ölçüyordu.
 *
 * GERÇEK: ekran (SettingsScreen / WelcomeScreen) + `useTeardownGuard` + `performEmergencyStop` + `apiClient` + `config`.
 * Sahte EN ALT katta: `global.fetch` (durdurma yollarına teyitli yanıt, ekranın açılış isteklerine hiç çözülmeyen söz) ve onay
 * penceresi (`platformConfirm`); ekran kabuğu (canlı veri bağlamı, profil / oturum bağlamı, süsler) sahte.
 * ⚠️ Yalnız KAPI: ACİL DURDUR / STOP davranışı değişmez; bu dosya ürün koduna dokunmaz.
 */
const mockOnay = jest.fn(async (..._a: unknown[]) => true);
const mockSetUserMode = jest.fn();
const mockLogout = jest.fn();
const olaylar: string[] = [];
let mockCanli: { snapshot: Record<string, unknown>; donanimBelirsiz: boolean };

jest.mock("@/services/apiClient", () => ({
  ...jest.requireActual("@/services/apiClient"),
  platformConfirm: (...a: unknown[]) => mockOnay(...a),
  platformAlert: jest.fn(),
}));
jest.mock("@/services/deviceRegistry", () => ({ getRemoteUrlForDevice: jest.fn(async () => null) }));
jest.mock("@/services/hesapGecisi", () => ({ onaySonrasiEngel: jest.fn(async () => null) }));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("@/services/pairing", () => ({ cihazaBaglan: jest.fn(), eslesmeMesaji: jest.fn(() => "") }));
jest.mock("@/services/discovery", () => ({
  checkHealth: jest.fn(() => new Promise(() => {})),
  discoverBackend: jest.fn(() => new Promise(() => {})),
}));
jest.mock("@/services/supabaseAuth", () => ({ updateProfile: jest.fn() }));
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ ...mockCanli, reconnect: jest.fn(), wsConnected: true }),
}));
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({
    userMode: "veterinarian",
    setUserMode: (m: unknown) => {
      olaylar.push(`setUserMode:${String(m)}`);
      mockSetUserMode(m);
    },
    isExpert: true,
    isResearcher: false,
  }),
}));
jest.mock("@/context/AuthContext", () => ({
  useAuth: () => ({
    session: { email: "op@klinik.com" },
    logout: () => {
      olaylar.push("logout");
      mockLogout();
    },
  }),
}));
jest.mock("@/context/EntitlementContext", () => ({
  useEntitlement: () => ({ tier: "pro", trialing: false, trialDaysLeft: 0, realtime: true, research: false, dogrulanamadi: false }),
}));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/components/ui/AuroraBackground", () => ({ AuroraBackground: () => null }));
jest.mock("@/components/ui/GlobalEmergencyStop", () => ({ GlobalEmergencyStop: () => null }));
jest.mock("@/components/ui/EstopMandalBandi", () => ({ EstopMandalBandi: () => null }));
jest.mock("expo-blur", () => ({ BlurView: () => null }));
jest.mock("expo-linear-gradient", () => ({ LinearGradient: () => null }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/hooks/useResponsive", () => ({
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  useResponsive: () => require("@/hooks/__tests__/responsiveMock").sahteMasaustu(),
}));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { updateServiceConfig } from "@/services/config";
import { SettingsScreen } from "@/screens/SettingsScreen";
import { WelcomeScreen } from "@/screens/WelcomeScreen";

const DURDURMA = /\/hardware\/emergency_stop|\/hardware\/command|\/session\/stop/;
const ESTOP_DORTLU = ["/api/hardware/command", "/api/hardware/emergency_stop", "/api/hardware/emergency_stop", "/api/session/stop"];
const CALISIYOR = {
  stm: "online",
  coils: [1, 2, 3].map((id) => ({ id, connected: true, running: id === 1 })),
  activeTreatment: { isActive: true, mode: "Manuel" },
};
const BOSTA = { stm: "online", coils: [1, 2, 3].map((id) => ({ id, connected: true, running: false })), activeTreatment: { isActive: false } };

beforeEach(() => {
  olaylar.length = 0;
  mockOnay.mockReset().mockImplementation(async () => true);
  mockSetUserMode.mockReset();
  mockLogout.mockReset();
  mockCanli = { snapshot: CALISIYOR, donanimBelirsiz: false };
  (global as { fetch: unknown }).fetch = jest.fn((url: string) => {
    const yol = String(url).replace(/^https?:\/\/[^/]+/, "");
    if (!DURDURMA.test(yol)) return new Promise(() => {}); // ekranın açılış istekleri bu kapının konusu değil
    olaylar.push(`fetch:${yol}`);
    const g = { confirmed: true, status: "success" };
    return Promise.resolve({ ok: true, status: 200, json: async () => g, text: async () => JSON.stringify(g) });
  });
  expect(updateServiceConfig("http://192.168.1.5:8000")).toBe(true);
  jest.spyOn(console, "error").mockImplementation(() => {});
  jest.spyOn(console, "warn").mockImplementation(() => {});
});
afterEach(() => jest.restoreAllMocks());

const durdurmalar = () =>
  olaylar
    .filter((o) => o.startsWith("fetch:"))
    .map((o) => o.slice(6))
    .sort();

type Yer = { ad: string; ciz: () => ReturnType<typeof render>; bas: (u: ReturnType<typeof render>) => void; sokum: string };
const YERLER: Yer[] = [
  {
    ad: "Ayarlar → Farklı Bir Profile Geçiş Yap",
    ciz: () => render(<SettingsScreen />),
    bas: (u) => fireEvent.press(u.getByText("Farklı Bir Profile Geçiş Yap")),
    sokum: "setUserMode:null",
  },
  {
    ad: "Karşılama → Çıkış yap",
    ciz: () => render(<WelcomeScreen />),
    bas: (u) => fireEvent.press(u.getByLabelText("Çıkış yap")),
    sokum: "logout",
  },
];

describe.each(YERLER)("İG-6.31 — $ad", ({ ciz, bas, sokum }) => {
  it("KRİTİK: bobin ÇALIŞIRKEN önce ONAY, kabulde ÖNCE ACİL DURDUR (4 istek) sonra söküm", async () => {
    const u = ciz();
    await act(async () => {
      bas(u);
    });
    await act(async () => {});
    expect(mockOnay).toHaveBeenCalledTimes(1);
    expect(mockOnay.mock.calls[0][0]).toBe("Seans sürüyor");
    expect(durdurmalar()).toEqual(ESTOP_DORTLU);
    const sokumSirasi = olaylar.indexOf(sokum);
    expect(sokumSirasi).toBeGreaterThan(-1);
    expect(olaylar.slice(0, sokumSirasi).filter((o) => o.startsWith("fetch:")).length).toBe(4); // durdurma sökümden ÖNCE
    u.unmount();
  });

  it("KRİTİK: onay REDDEDİLİRSE söküm YOK (ekran ve ACİL DURDUR yerinde kalır)", async () => {
    mockOnay.mockImplementation(async () => false);
    const u = ciz();
    await act(async () => {
      bas(u);
    });
    await act(async () => {});
    expect(mockOnay).toHaveBeenCalledTimes(1);
    expect(olaylar).not.toContain(sokum);
    u.unmount();
  });

  it("KRİTİK: ekran BOŞTA açılıp sonra bobin çalışınca da kapı TAZE durumu görür (bayat kapanış yok)", async () => {
    mockCanli = { snapshot: BOSTA, donanimBelirsiz: false };
    const u = ciz();
    await act(async () => {});
    mockCanli = { snapshot: CALISIYOR, donanimBelirsiz: false };
    u.rerender(sokum === "logout" ? <WelcomeScreen /> : <SettingsScreen />);
    await act(async () => {
      bas(u);
    });
    await act(async () => {});
    expect(mockOnay).toHaveBeenCalledTimes(1);
    expect(durdurmalar()).toEqual(ESTOP_DORTLU);
    u.unmount();
  });

  it("KARŞIT: donanım BOŞTAYKEN kapı engellemez — onaysız söküm, durdurma isteği yok", async () => {
    mockCanli = { snapshot: BOSTA, donanimBelirsiz: false };
    const u = ciz();
    await act(async () => {
      bas(u);
    });
    await act(async () => {});
    expect(mockOnay).not.toHaveBeenCalled();
    expect(durdurmalar()).toEqual([]);
    expect(olaylar).toContain(sokum);
    u.unmount();
  });
});
