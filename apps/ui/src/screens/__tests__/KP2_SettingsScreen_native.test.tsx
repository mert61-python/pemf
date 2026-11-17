/**
 * KP-2 · src/screens/SettingsScreen.tsx (YEREL / telefon yolu, Platform.OS = "ios") · sözleşmeler:
 *  - açılışta kayıtlı sunucu adresi (AsyncStorage) REST tabanına uygulanır ve alanda görünür;
 *  - "Bağlantıyı Test Et": PEMF kimliği (service === "PEMF-Vet") doğrulanan adres taban + kalıcı adres olur, WS yeniden bağlanır;
 *    kimliksiz host (router) → "PEMF cihazı bulunamadı", taban DEĞİŞMEZ; biçimi bozuk adres → "Geçersiz adres", ayar BOZULMAZ;
 *  - "Ağı Yeniden Tara": keşif merdiveni kayıtlı adresi doğrularsa şema/port ayıklanmış IP gösterilir + WS yeniden bağlanır;
 *    hiçbir basamakta cihaz yoksa "Ağda PEMF cihazı bulunamadı";
 *  - "Cihaza Bağlan" (eşleştirme kodu): bulut çözümü + kimlik + jeton takası başarılı → taban tünel adresine geçer, "bağlandı";
 *  - kopyalama (pano yok): değer "elle kopyalayın" metniyle yerel uyarı penceresinde;
 *  - "Ayarları Kaydet": kimliği doğrulanan ama biçimi geçersiz adres → "Geçersiz sunucu adresi — kaydedilmedi", /settings/ GİTMEZ;
 *  - profil düzenleme: TÜM alanlar yüklenir, gizli profil alanları kaydederken KORUNUR (veri kaybı yok), ad/soyad boşsa Supabase'e
 *    GİDİLMEZ, Supabase hatası kullanıcıya eşlenmiş metinle söylenir, İptal formu kapatır.
 * GERÇEK: SettingsScreen, apiClient, config, discovery (checkHealth / discoverBackend), pairing (cihazaBaglan / eslesmeMesaji),
 *         deviceRegistry, duzHttpKapisi, supabaseAuth (updateProfile → mapError).
 * SAHTE (en alt kat / ekran dışı): fetch, Supabase istemcisi (`createClient` → rpc / auth.updateUser), yerel mDNS modülü
 *   (react-native-zeroconf: jest'te yerel modül yok → kurucu atar), Alert, Platform.OS, ekranın bağlamları (kip, oturum, canlı veri).
 */
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
const mockKip = { isExpert: true, isResearcher: false };
jest.mock("@/context/UserModeContext", () => ({
  useUserMode: () => ({ setUserMode: jest.fn(), ...mockKip }),
}));
const mockOturum: { session: unknown } = { session: null };
jest.mock("@/context/AuthContext", () => ({ useAuth: () => mockOturum }));
const mockReconnect = jest.fn();
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ reconnect: mockReconnect, wsConnected: false }) }));
jest.mock("@/hooks/useTeardownGuard", () => ({ useTeardownGuard: () => async () => true }));
const mockUpdateUser = jest.fn();
const mockRpc = jest.fn();
jest.mock("@supabase/supabase-js", () => ({
  createClient: () => ({
    auth: {
      updateUser: (...a: unknown[]) => mockUpdateUser(...a),
      getSession: async () => ({ data: { session: null } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => undefined } } }),
    },
    rpc: (...a: unknown[]) => mockRpc(...a),
  }),
}));
// Yerel ağ bilgisi (platform katı): telefon 192.168.1.23 ile Wi-Fi'de. Gerçek modül jest'te yerel köprüsüz kendi iç durumunda
// işlenmeyen ret üretiyor (ölçüldü: "Cannot read properties of undefined (reading 'isInternetReachable')").
jest.mock("@react-native-community/netinfo", () => ({
  __esModule: true,
  default: { fetch: async () => ({ type: "wifi", details: { ipAddress: "192.168.1.23" } }) },
}));
jest.mock("react-native-zeroconf", () => ({
  __esModule: true,
  default: function Zeroconf() {
    throw new Error("RNZeroconf yerel modülü yok (jest)");
  },
}));

import React from "react";
import { Alert, Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";

import { SettingsScreen } from "@/screens/SettingsScreen";
import { serviceConfig, updateServiceConfig } from "@/services/config";

const t = (k: string, o?: Record<string, unknown>) => i18n.t(k, o as never) as unknown as string;
const PEMF = (deviceId: string) => ({ service: "PEMF-Vet", status: "online", deviceId });

type Cagri = { url: string; yontem: string; govde: unknown };
let cagrilar: Cagri[];
/** URL → [durum, gövde]; tanımsızsa 404. */
let yanitlar: Record<string, [number, unknown]>;

function sahteYanit(veri: unknown, durum = 200) {
  const govde = JSON.stringify(veri);
  return {
    ok: durum >= 200 && durum < 300,
    status: durum,
    headers: { get: () => "application/json" },
    text: async () => govde,
    json: async () => JSON.parse(govde),
  };
}

const orijinalOS = Platform.OS;
let alertCasus: jest.SpyInstance;
beforeAll(() => {
  Object.defineProperty(Platform, "OS", { configurable: true, get: () => "ios" });
});
afterAll(() => {
  Object.defineProperty(Platform, "OS", { configurable: true, get: () => orijinalOS });
});

beforeEach(async () => {
  jest.clearAllMocks();
  await AsyncStorage.clear();
  updateServiceConfig("http://127.0.0.1:8000");
  serviceConfig.apiToken = "";
  mockKip.isExpert = true;
  mockKip.isResearcher = false;
  mockOturum.session = null;
  mockUpdateUser.mockResolvedValue({ data: {}, error: null });
  mockRpc.mockResolvedValue({ data: [], error: null });
  alertCasus = jest.spyOn(Alert, "alert").mockImplementation(() => {});
  cagrilar = [];
  yanitlar = {
    "http://127.0.0.1:8000/api/health": [200, { ...PEMF("yerel-cihaz"), pairingCode: "KP2KOD", deviceId: "cihaz-kp2-0001", cloudRegistry: "ok" }],
  };
  (global as unknown as { fetch: unknown }).fetch = jest.fn(async (url: string, init?: RequestInit) => {
    const u = String(url).split("?")[0];
    cagrilar.push({ url: u, yontem: (init?.method || "GET").toUpperCase(), govde: init?.body ? JSON.parse(String(init.body)) : null });
    const y = yanitlar[u];
    return y ? sahteYanit(y[1], y[0]) : sahteYanit({ detail: "Not Found" }, 404);
  });
});

afterEach(async () => {
  alertCasus.mockRestore();
  updateServiceConfig("http://127.0.0.1:8000");
  serviceConfig.apiToken = "";
  await AsyncStorage.clear();
});

async function ciz() {
  const u = render(<SettingsScreen />);
  await act(async () => {});
  await act(async () => {});
  return u;
}
const toastlar = () => mockToast.mock.calls.map((c) => [String(c[0]), c[1]] as [string, unknown]);
const MANUEL = () => t("ayarlar.baglanti.manuelEtiketi");

describe("açılış — kayıtlı sunucu adresi", () => {
  test("kayıtlı @pemf_server_address yerelde REST tabanına uygulanır ve manuel alanda görünür", async () => {
    await AsyncStorage.setItem("@pemf_server_address", "192.168.1.60");
    yanitlar["http://192.168.1.60:8000/api/health"] = [200, PEMF("d60")];
    const u = await ciz();
    expect(serviceConfig.apiBaseUrl).toBe("http://192.168.1.60:8000/api");
    expect(u.getByLabelText(MANUEL()).props.value).toBe("192.168.1.60");
  });

  test("yalnız eski @pemf_server_ip anahtarı varsa o okunur ve uygulanır", async () => {
    await AsyncStorage.setItem("@pemf_server_ip", "10.0.0.7");
    const u = await ciz();
    expect(serviceConfig.apiBaseUrl).toBe("http://10.0.0.7:8000/api");
    expect(u.getByLabelText(MANUEL()).props.value).toBe("10.0.0.7");
  });
});

describe("Bağlantıyı Test Et (yerel) — yalnız PEMF kimliği doğrulanan adres taban olur", () => {
  async function testEt(adres: string) {
    const u = await ciz();
    fireEvent.changeText(u.getByLabelText(MANUEL()), adres);
    await act(async () => { fireEvent.press(u.getByText(t("ayarlar.baglanti.testEt"))); });
    await act(async () => {});
    return u;
  }

  test("PEMF-Vet yanıtı → taban + kalıcı adres + WS yeniden bağlanır, 'Bağlantı başarılı', 'Bağlı' rozeti", async () => {
    yanitlar["http://192.168.1.70:8000/api/health"] = [200, PEMF("d70")];
    const u = await testEt("192.168.1.70");
    await waitFor(() => expect(toastlar()).toEqual([[t("ayarlar.baglanti.basarili"), "success"]]));
    expect(serviceConfig.apiBaseUrl).toBe("http://192.168.1.70:8000/api");
    expect(await AsyncStorage.getItem("@pemf_server_address")).toBe("192.168.1.70");
    expect(mockReconnect).toHaveBeenCalledTimes(1);
    expect(u.getByText(t("ayarlar.baglanti.durumBagli"))).toBeTruthy();
  });

  // KP-7 B (işlev ölçüsü): kalıcı adres YAZILAMAZSA (depo arızası) bağlantı yine kurulur — taban + WS bu oturumda yeni cihazda,
  // 'Bağlantı başarılı' (yalnız bir sonraki açılışta adres hatırlanmaz).
  test("kalıcı adres yazılamasa da bağlantı kurulur: taban + WS yeni cihazda, 'Bağlantı başarılı'", async () => {
    yanitlar["http://192.168.1.71:8000/api/health"] = [200, PEMF("d71")];
    // ⚠️ AsyncStorage.setItem zaten bir jest.fn (depo sahtesi): `spyOn` + `mockRestore` onun ASIL uygulamasını siler ve sonraki
    // testlerin deposu bozulur (ölçüldü: "Ağı Yeniden Tara" kırmızı). Asıl uygulama saklanır, yalnız adres anahtarı reddedilir, geri konur.
    const yaz = AsyncStorage.setItem as unknown as jest.Mock;
    const gercek = yaz.getMockImplementation()!;
    yaz.mockImplementation((k: string, v: string) =>
      k === "@pemf_server_address" ? Promise.reject(new Error("depo yazılamadı")) : gercek(k, v),
    );
    try {
      await testEt("192.168.1.71");
      await waitFor(() => expect(toastlar()).toEqual([[t("ayarlar.baglanti.basarili"), "success"]]));
      expect(yaz).toHaveBeenCalledWith("@pemf_server_address", "192.168.1.71");
      expect(await AsyncStorage.getItem("@pemf_server_address")).toBeNull();
      expect(serviceConfig.apiBaseUrl).toBe("http://192.168.1.71:8000/api");
      expect(mockReconnect).toHaveBeenCalledTimes(1);
    } finally {
      yaz.mockImplementation(gercek);
    }
  });

  test("/api/health 200 ama PEMF kimliği YOK (router paneli) → 'PEMF cihazı bulunamadı', taban/kalıcı adres DEĞİŞMEZ", async () => {
    yanitlar["http://192.168.1.1:8000/api/health"] = [200, { status: "online" }];
    const u = await testEt("192.168.1.1");
    await waitFor(() => expect(toastlar()).toEqual([[t("ayarlar.baglanti.cihazYok"), "error"]]));
    expect(serviceConfig.apiBaseUrl).toBe("http://127.0.0.1:8000/api");
    expect(await AsyncStorage.getItem("@pemf_server_address")).toBeNull();
    expect(mockReconnect).not.toHaveBeenCalled();
    expect(u.getByText(t("ayarlar.baglanti.durumBaglanamadi"))).toBeTruthy();
  });

  test("kimlik doğrulansa da biçimi geçersiz adres ('/' içerir) → 'Geçersiz adres biçimi', ayar BOZULMAZ, kalıcı yazım yok", async () => {
    yanitlar["http://192.168.1.1/kotu:8000/api/health"] = [200, PEMF("dX")];
    await testEt("192.168.1.1/kotu");
    await waitFor(() => expect(toastlar()).toEqual([[t("ayarlar.baglanti.gecersizAdres"), "error"]]));
    expect(serviceConfig.apiBaseUrl).toBe("http://127.0.0.1:8000/api");
    expect(await AsyncStorage.getItem("@pemf_server_address")).toBeNull();
    expect(mockReconnect).not.toHaveBeenCalled();
  });
});

describe("Ağı Yeniden Tara (yerel) — gerçek keşif merdiveni", () => {
  test("kayıtlı adres doğrulanınca şema/port ayıklanmış IP gösterilir, 'cihaz bulundu' + WS yeniden bağlanır", async () => {
    await AsyncStorage.setItem("@pemf_server_address", "http://192.168.1.80:8000");
    yanitlar["http://192.168.1.80:8000/api/health"] = [200, PEMF("d80")];
    const u = await ciz();
    await act(async () => { fireEvent.press(u.getByText(t("ayarlar.baglanti.yenidenTara"))); });
    await waitFor(() => expect(mockReconnect).toHaveBeenCalledTimes(1));
    expect(toastlar()).toEqual([
      [t("ayarlar.baglanti.taraniyor"), "info"],
      [t("ayarlar.baglanti.bulundu", { adres: "192.168.1.80" }), "success"],
    ]);
    expect(u.getByLabelText(MANUEL()).props.value).toBe("192.168.1.80");
    expect(u.getByText(t("ayarlar.baglanti.durumBagli"))).toBeTruthy();
  });

  test("hiçbir basamakta (kayıtlı / mDNS / uzak / alt ağ) PEMF yok → 'Ağda PEMF cihazı bulunamadı' (info), 'Bağlanamadı'", async () => {
    delete yanitlar["http://127.0.0.1:8000/api/health"];
    const u = await ciz();
    await act(async () => { fireEvent.press(u.getByText(t("ayarlar.baglanti.yenidenTara"))); });
    await waitFor(() => expect(toastlar()).toHaveLength(2), { timeout: 15000 });
    expect(toastlar()[1]).toEqual([t("ayarlar.baglanti.agdaYok"), "info"]);
    expect(mockReconnect).not.toHaveBeenCalled();
    expect(u.getByText(t("ayarlar.baglanti.durumBaglanamadi"))).toBeTruthy();
    // alt ağ taraması gerçekten koştu (son çare basamağı) ama hiçbir adres uygulanmadı
    expect(cagrilar.some((c) => /^http:\/\/192\.168\.1\.\d+:8000\/api\/health$/.test(c.url))).toBe(true);
    expect(serviceConfig.apiBaseUrl).toBe("http://127.0.0.1:8000/api");
  });
});

describe("Cihaza Bağlan (eşleştirme kodu) — başarılı yol", () => {
  test("bulut çözümü + PEMF kimliği + jeton takası → taban tünele geçer, adres alanda, 'bağlandı', WS yeniden bağlanır", async () => {
    const TUNEL = "https://kp2-cihaz.trycloudflare.com";
    mockRpc.mockResolvedValue({
      data: [{ device_id: "DEV-KP2", name: "Klinik", tunnel_url: TUNEL, local_ip: null, last_seen: new Date().toISOString() }],
      error: null,
    });
    yanitlar[`${TUNEL}/api/health`] = [200, PEMF("DEV-KP2")];
    yanitlar[`${TUNEL}/api/auth/exchange`] = [200, { token: "kp2-jeton" }];
    const u = await ciz();
    fireEvent.changeText(u.getByLabelText(t("ayarlar.eslestirme.uzakBaglanEtiketi")), " abc 123 ");
    expect(u.getByLabelText(t("ayarlar.eslestirme.uzakBaglanEtiketi")).props.value).toBe("ABC123");
    await act(async () => { fireEvent.press(u.getByText(t("ayarlar.eslestirme.baglan"))); });
    await waitFor(() => expect(toastlar()).toEqual([[t("ayarlar.eslestirme.sonucOk"), "success"]]));
    expect(mockRpc).toHaveBeenCalledWith("resolve_device", { p_code: "ABC123" });
    expect(cagrilar.find((c) => c.url === `${TUNEL}/api/auth/exchange`)?.govde).toEqual({ code: "ABC123" });
    expect(serviceConfig.apiBaseUrl).toBe(`${TUNEL}/api`);
    expect(serviceConfig.apiToken).toBe("kp2-jeton");
    expect(mockReconnect).toHaveBeenCalledTimes(1);
    expect(u.getByLabelText(MANUEL()).props.value).toBe(TUNEL);
    expect(u.getByText(t("ayarlar.baglanti.durumBagli"))).toBeTruthy();
    expect(u.getByText(t("ayarlar.eslestirme.baglan"))).toBeTruthy(); // "Bağlanıyor..." kilidi kalktı
  });
});

describe("kopyalama (yerel — pano kütüphanesi yok)", () => {
  test("eşleştirme kodu ve cihaz kimliği 'elle kopyalayın' metniyle yerel uyarı penceresinde gösterilir", async () => {
    const u = await ciz();
    await waitFor(() => expect(u.getByText("KP2KOD")).toBeTruthy());
    fireEvent.press(u.getByText("KP2KOD"));
    expect(alertCasus).toHaveBeenLastCalledWith(t("ayarlar.eslestirme.kod"), t("ayarlar.kopyala.elle", { deger: "KP2KOD" }));
    fireEvent.press(u.getByText("cihaz-kp2-0001"));
    expect(alertCasus).toHaveBeenLastCalledWith(
      t("ayarlar.eslestirme.cihazKimligi"),
      t("ayarlar.kopyala.elle", { deger: "cihaz-kp2-0001" }),
    );
    expect(mockToast).not.toHaveBeenCalled();
  });
});

describe("Ayarları Kaydet (yerel)", () => {
  test("kimliği doğrulanan ama biçimi geçersiz adres → 'Geçersiz sunucu adresi — kaydedilmedi', /settings/ GÖNDERİLMEZ", async () => {
    yanitlar["http://192.168.1.1/kotu:8000/api/health"] = [200, PEMF("dX")];
    const u = await ciz();
    fireEvent.changeText(u.getByLabelText(MANUEL()), "192.168.1.1/kotu");
    await act(async () => { fireEvent.press(u.getByText(t("ayarlar.kaydetDugme"))); });
    await waitFor(() => expect(u.getByText(t("ayarlar.baglanti.adresKaydedilmedi"))).toBeTruthy());
    expect(cagrilar.filter((c) => c.yontem === "POST" && /\/settings\/$/.test(c.url))).toEqual([]);
    expect(await AsyncStorage.getItem("@pemf_server_address")).toBeNull();
    expect(serviceConfig.apiBaseUrl).toBe("http://127.0.0.1:8000/api");
  });
});

// ── Profil düzenleme ─────────────────────────────────────────────────────────────────────────────────────────────────────────
const PROFIL = {
  first_name: "Ayşe", last_name: "Kaya", title: "Vet. Hekim", phone: "05550000000",
  clinic_name: "Pati Klinik", clinic_phone: "02320000000", city: "İzmir", district: "Bornova", address: "Kazım Dirik",
  institution: "İKÇÜ", department: "Biyomühendislik", academic_title: "Dr.",
};

describe("profil düzenleme — gizli profil alanları kaydederken SİLİNMEZ", () => {
  test("VETERİNER: form tüm alanlarla dolar; düzenlenenler + gizli araştırma alanları Supabase'e birlikte gider; başarı → form kapanır", async () => {
    mockOturum.session = { email: "ayse@klinik.com", profile: { ...PROFIL } };
    const u = await ciz();
    fireEvent.press(u.getByLabelText(t("ayarlar.hesap.duzenleEtiketi")));
    expect(u.getByPlaceholderText(t("ayarlar.hesap.ad")).props.value).toBe("Ayşe");
    expect(u.getByPlaceholderText(t("ayarlar.hesap.klinikAdi")).props.value).toBe("Pati Klinik");
    expect(u.queryByPlaceholderText(t("ayarlar.hesap.kurumOrnek"))).toBeNull();
    const yaz = (yer: string, v: string) => fireEvent.changeText(u.getByPlaceholderText(yer), v);
    yaz(t("ayarlar.hesap.ad"), "  Zeynep ");
    yaz(t("ayarlar.hesap.soyad"), "Demir ");
    yaz(t("ayarlar.hesap.unvanOrnek"), "Uzm. Vet.");
    yaz(t("ayarlar.hesap.cepTelefonu"), "05551112233");
    yaz(t("ayarlar.hesap.klinikAdi"), "Yeni Klinik");
    yaz(t("ayarlar.hesap.sehir"), "Ankara");
    yaz(t("ayarlar.hesap.ilce"), "Çankaya");
    yaz(t("ayarlar.hesap.acikAdres"), "Atatürk Blv. 1");
    yaz(t("ayarlar.hesap.klinikAcilTelefonOrnek"), "03120000000");
    await act(async () => { fireEvent.press(u.getByText(t("ayarlar.kaydet"))); });
    await waitFor(() => expect(toastlar()).toEqual([[t("ayarlar.hesap.guncellendi"), "success"]]));
    expect(mockUpdateUser).toHaveBeenCalledTimes(1);
    expect(mockUpdateUser.mock.calls[0][0]).toEqual({
      data: {
        first_name: "Zeynep", last_name: "Demir", full_name: "Zeynep Demir", title: "Uzm. Vet.", phone: "05551112233",
        clinic_name: "Yeni Klinik", clinic_phone: "03120000000", city: "Ankara", district: "Çankaya", address: "Atatürk Blv. 1",
        institution: "İKÇÜ", department: "Biyomühendislik", academic_title: "Dr.",
      },
    });
    expect(u.queryByPlaceholderText(t("ayarlar.hesap.ad"))).toBeNull();
    expect(u.getByLabelText(t("ayarlar.hesap.duzenleEtiketi"))).toBeTruthy();
  });

  test("ARAŞTIRMA: kurum/bölüm/ünvan düzenlenir, gizli klinik alanları AYNEN korunur", async () => {
    mockKip.isExpert = false;
    mockKip.isResearcher = true;
    mockOturum.session = { email: "ayse@klinik.com", profile: { ...PROFIL } };
    const u = await ciz();
    fireEvent.press(u.getByLabelText(t("ayarlar.hesap.duzenleEtiketi")));
    expect(u.queryByPlaceholderText(t("ayarlar.hesap.klinikAdi"))).toBeNull();
    fireEvent.changeText(u.getByPlaceholderText(t("ayarlar.hesap.kurumOrnek")), "ODTÜ");
    fireEvent.changeText(u.getByPlaceholderText(t("ayarlar.hesap.bolumOrnek")), "Fizik");
    fireEvent.changeText(u.getByPlaceholderText(t("ayarlar.hesap.akademikUnvanOrnek")), "Doç. Dr.");
    await act(async () => { fireEvent.press(u.getByText(t("ayarlar.kaydet"))); });
    await waitFor(() => expect(mockUpdateUser).toHaveBeenCalledTimes(1));
    const meta = mockUpdateUser.mock.calls[0][0].data;
    expect(meta).toMatchObject({ institution: "ODTÜ", department: "Fizik", academic_title: "Doç. Dr." });
    expect(meta).toMatchObject({ clinic_name: "Pati Klinik", clinic_phone: "02320000000", full_name: "Ayşe Kaya" });
  });

  test("ad boş (yalnız boşluk) → Supabase'e GİDİLMEZ, 'Ad ve soyad boş olamaz' (error), form açık kalır", async () => {
    mockOturum.session = { email: "ayse@klinik.com", profile: { ...PROFIL } };
    const u = await ciz();
    fireEvent.press(u.getByLabelText(t("ayarlar.hesap.duzenleEtiketi")));
    fireEvent.changeText(u.getByPlaceholderText(t("ayarlar.hesap.soyad")), "   ");
    await act(async () => { fireEvent.press(u.getByText(t("ayarlar.kaydet"))); });
    expect(mockUpdateUser).not.toHaveBeenCalled();
    expect(toastlar()).toEqual([[t("ayarlar.hesap.adSoyadBos"), "error"]]);
    expect(u.getByPlaceholderText(t("ayarlar.hesap.soyad")).props.value).toBe("   ");
  });

  test("Supabase ağ hatası → eşlenmiş 'sunucuya ulaşılamadı' metni (error); eksik profil alanları boş dizeyle gider; form AÇIK", async () => {
    mockOturum.session = { email: "ali@klinik.com", profile: { first_name: "Ali", last_name: "Veli" } };
    mockUpdateUser.mockResolvedValue({ data: null, error: { message: "Failed to fetch" } });
    const u = await ciz();
    fireEvent.press(u.getByLabelText(t("ayarlar.hesap.duzenleEtiketi")));
    expect(u.getByPlaceholderText(t("ayarlar.hesap.klinikAdi")).props.value).toBe("");
    await act(async () => { fireEvent.press(u.getByText(t("ayarlar.kaydet"))); });
    await waitFor(() => expect(toastlar()).toEqual([[t("giris.hata.sunucuyaUlasilamadi"), "error"]]));
    expect(mockUpdateUser.mock.calls[0][0].data).toMatchObject({ first_name: "Ali", clinic_name: "", institution: "", city: "" });
    expect(u.getByPlaceholderText(t("ayarlar.hesap.ad")).props.value).toBe("Ali");
  });

  test("İptal → form kapanır, Supabase çağrılmaz, salt-okunur görünüm (eski ad) döner", async () => {
    mockOturum.session = { email: "ayse@klinik.com", profile: { ...PROFIL } };
    const u = await ciz();
    fireEvent.press(u.getByLabelText(t("ayarlar.hesap.duzenleEtiketi")));
    fireEvent.changeText(u.getByPlaceholderText(t("ayarlar.hesap.ad")), "Değişti");
    fireEvent.press(u.getByText(t("ayarlar.iptal")));
    expect(mockUpdateUser).not.toHaveBeenCalled();
    expect(u.queryByPlaceholderText(t("ayarlar.hesap.ad"))).toBeNull();
    expect(u.queryByText("Değişti")).toBeNull();
    expect(u.getByLabelText(t("ayarlar.hesap.duzenleEtiketi"))).toBeTruthy();
  });
});
