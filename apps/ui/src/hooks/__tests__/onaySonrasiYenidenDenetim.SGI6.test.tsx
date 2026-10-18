// Author: mertaygn, cglrgrkn
/**
 * S-SGI.6 (sahip kararı 2026-10-18: "Evet, yeniden denetle") — ONAY PENCERESİ AÇIKKEN BAŞLAYAN SEANS.
 * =====================================================================================================
 * Ölçülen boşluk: boşta "Çıkış Yap" onayı (`confirmWhenIdle`) ve "E-posta hesapları"nda ETKİN hesaptan çıkış onayı, durumu pencere
 * AÇILMADAN ÖNCE denetliyordu. Web'de `window.confirm` JS'i bloklar, yerelde `Alert` beklerken çağıranın kapanışındaki anlık görüntü
 * güncellenmez → pencere açıkken başka istemci / AI Pro seansı başlatırsa "Evet" kabuğu söküyor, operatör ACİL DURDUR'u kaybediyordu.
 *
 * SÖZLEŞME:
 *  · onay VERİLDİKTEN SONRA durum backend'den TAZE okunur (`/dashboard-snapshot`) — onaydan ÖNCE değil;
 *  · taze durumda çalışan bobin / aktif seans → eylem İPTAL + neden;
 *  · backend'e ulaşılamazsa (null / atış) bugünkü davranış: devam (çevrimdışı çıkış kilitlenmez);
 *  · onay istenmeyen yol (confirmWhenIdle yok) ve park edilmiş hesaptan çıkış ağ isteği YAPMAZ.
 */
let mockSnap: any;
let mockAuth: any;
let mockOp: any;
const sira: string[] = [];
const mockConfirm = jest.fn(async (..._a: unknown[]) => { sira.push("onay"); return true; });
const mockAlert = jest.fn();
let mockTaze: () => Promise<unknown>;
const mockApiGet = jest.fn(async (yol: string, _fb: unknown, _o?: unknown) => { sira.push(`get:${yol}`); return mockTaze(); });

jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => (mockApiGet as any)(...a),
  platformAlert: (...a: unknown[]) => (mockAlert as any)(...a),
  platformConfirm: (...a: unknown[]) => (mockConfirm as any)(...a),
  hesapKusagiArtir: jest.fn(),
  setAuthBearer: jest.fn(),
  setEntitlementHeaders: jest.fn(),
}));
jest.mock("@/services/emergencyStop", () => ({
  performEmergencyStop: jest.fn(async () => ({ confirmed: true })),
  EMERGENCY_STOP_UNCONFIRMED_TITLE: "UYARI",
  EMERGENCY_STOP_UNCONFIRMED_BODY: "gövde",
  EMERGENCY_STOP_KART_RED_TITLE: "RED",
  EMERGENCY_STOP_KART_RED_BODY: "red gövde",
}));
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: mockSnap, donanimBelirsiz: false }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => mockAuth }));
jest.mock("@/context/OperatorContext", () => ({ useOperatorOptional: () => mockOp }));
jest.mock("@/services/supabaseAuth", () => ({
  supabaseAuth: { auth: {} },
  oturumDeposu: { getItem: async () => null, setItem: async () => undefined, removeItem: async () => undefined },
}));
jest.mock("@/components/ui/GlobalEmergencyStop", () => ({ GlobalEmergencyStop: () => null }));

import React from "react";
import { act, fireEvent, render, renderHook } from "@testing-library/react-native";
import { useTeardownGuard } from "@/hooks/useTeardownGuard";
import { HesapMenusu } from "@/components/domain/HesapMenusu";
import { ONAY_SIRASINDA_SEANS_BASLADI } from "@/services/hesapGecisi";

const BOSTA = { coils: [{ id: 1, running: false }], activeTreatment: { isActive: false } };
const BOBIN_CALISIYOR = { coils: [{ id: 1, running: false }, { id: 2, running: true }], activeTreatment: { isActive: false } };
const SEANS_AKTIF = { coils: [{ id: 1, running: false }], activeTreatment: { isActive: true } };
const BOSTA_ONAY = { confirmWhenIdle: { title: "Çıkış", body: "Çıkılsın mı?" } };

beforeEach(() => {
  sira.length = 0;
  mockConfirm.mockClear();
  mockAlert.mockClear();
  mockApiGet.mockClear();
  mockSnap = BOSTA;
  mockTaze = async () => BOSTA;
  mockOp = { multiUser: true, active: { email: "dr.x@klinik.com" }, lock: jest.fn(() => sira.push("kilit")) };
  mockAuth = {
    session: { email: "a@klinik.com" },
    hesaplar: ["a@klinik.com", "b@klinik.com"],
    hesabaGec: jest.fn(async () => ({ ok: true })),
    hesaptanCik: jest.fn(async () => { sira.push("cik"); return { ok: true }; }),
    hesapEkle: jest.fn(),
  };
});

const koru = async (opts: any = BOSTA_ONAY) => {
  const { result } = renderHook(() => useTeardownGuard());
  return result.current("Çıkış yapmak", opts);
};

describe("teardown koruması — boşta onay yolu", () => {
  it("KRİTİK: pencere açıkken BOBİN çalışmaya başladıysa söküm İPTAL + neden; durum onaydan SONRA okunur", async () => {
    mockTaze = async () => BOBIN_CALISIYOR;
    await expect(koru()).resolves.toBe(false);
    expect(sira).toEqual(["onay", "get:/dashboard-snapshot"]);
    expect(mockAlert).toHaveBeenCalledWith("İşlem iptal edildi", ONAY_SIRASINDA_SEANS_BASLADI);
  });

  it("KRİTİK: pencere açıkken SEANS başladıysa (bobin bayrağı henüz yok) söküm İPTAL", async () => {
    mockTaze = async () => SEANS_AKTIF;
    await expect(koru()).resolves.toBe(false);
    expect(mockAlert).toHaveBeenCalledTimes(1);
  });

  it("KARŞIT: taze durum hâlâ boşta → izin verilir, uyarı yok", async () => {
    await expect(koru()).resolves.toBe(true);
    expect(mockApiGet).toHaveBeenCalledTimes(1);
    expect(mockAlert).not.toHaveBeenCalled();
  });

  it("KARŞIT çevrimdışı: backend null döner ya da atarsa bugünkü davranış (devam) — çıkış kilitlenmez", async () => {
    mockTaze = async () => null;
    await expect(koru()).resolves.toBe(true);
    mockTaze = async () => { throw new Error("ağ yok"); };
    await expect(koru()).resolves.toBe(true);
    expect(mockAlert).not.toHaveBeenCalled();
  });

  it("onay REDDEDİLİRSE ağ isteği yapılmaz; onay istenmeyen yolda (confirmWhenIdle yok) da yapılmaz", async () => {
    mockConfirm.mockImplementationOnce(async () => false);
    await expect(koru()).resolves.toBe(false);
    await expect(koru(null)).resolves.toBe(true);
    expect(mockApiGet).not.toHaveBeenCalled();
  });
});

describe("E-posta hesapları — etkin hesaptan çıkış", () => {
  const ciz = () => render(<HesapMenusu visible onClose={jest.fn()} onTumundenCik={jest.fn()} />);

  it("KRİTİK: onay penceresi açıkken seans başladıysa ETKİN hesaptan çıkış İPTAL + neden; hekim kilitlenmez", async () => {
    mockTaze = async () => BOBIN_CALISIYOR;
    const u = ciz();
    await act(async () => { fireEvent.press(u.getByLabelText("a@klinik.com hesabından çık")); });
    expect(mockAuth.hesaptanCik).not.toHaveBeenCalled();
    expect(mockOp.lock).not.toHaveBeenCalled();
    expect(u.getByTestId("hesap-menusu-hata").props.children).toBe(ONAY_SIRASINDA_SEANS_BASLADI);
    expect(sira).toEqual(["onay", "get:/dashboard-snapshot"]);
  });

  it("KARŞIT: taze durum boşta → onay → hekim kilidi → çıkış (sıra korunur)", async () => {
    const u = ciz();
    await act(async () => { fireEvent.press(u.getByLabelText("a@klinik.com hesabından çık")); });
    expect(sira).toEqual(["onay", "get:/dashboard-snapshot", "kilit", "cik"]);
  });

  it("KARŞIT: PARK edilmiş hesaptan çıkış etkin hesabı sökmez → taze okuma YOK, seans sürse de çıkılır", async () => {
    mockTaze = async () => BOBIN_CALISIYOR;
    const u = ciz();
    await act(async () => { fireEvent.press(u.getByLabelText("b@klinik.com hesabından çık")); });
    expect(mockApiGet).not.toHaveBeenCalled();
    expect(mockAuth.hesaptanCik).toHaveBeenCalledWith("b@klinik.com");
  });
});
