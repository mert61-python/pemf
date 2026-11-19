// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) B3 — modül araç takımı `useModul`: açılışta + saniyede bir durum; komut başarılıysa hata temizlenir ve durum tazelenir;
 * başarısızsa sunucu hata kodu; panel söküldükten sonra gelen yanıt durum yazmaz.
 */
const mockApi = {
  durum: jest.fn(),
  uygula: jest.fn(),
  baslat: jest.fn(),
  durdur: jest.fn(),
};
jest.mock("@/services/moduller", () => ({
  get modulApi() {
    return mockApi; // getter: fabrika hoist edilir, sabit henüz TDZ'de (KP-8 dersi)
  },
}));

import { act, renderHook } from "@testing-library/react-native";
import { DURUM_ARALIK_MS, useModul } from "@/moduller/arac";

describe("GA useModul", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    for (const f of Object.values(mockApi)) f.mockReset();
    mockApi.durum.mockResolvedValue({ tamam: true, veri: { etkin: "ornek", surucu: { bobin: false } } });
  });
  afterEach(() => jest.useRealTimers());

  it("durum açılışta + 1 sn'de bir; komut başarı / hata", async () => {
    expect(DURUM_ARALIK_MS).toBe(1000);
    const { result, unmount } = renderHook(() => useModul());
    await act(async () => {});
    expect(result.current.durum).toEqual({ bobin: false });
    expect(mockApi.durum).toHaveBeenCalledTimes(1);
    await act(async () => {
      jest.advanceTimersByTime(1000);
    });
    expect(mockApi.durum).toHaveBeenCalledTimes(2);
    mockApi.uygula.mockResolvedValue({ tamam: false, hata: { kod: "ayarSinirDisi", alan: "frekans_hz" } });
    let ok = true;
    await act(async () => {
      ok = await result.current.uygula({ frekans_hz: 9999 });
    });
    expect(ok).toBe(false);
    expect(result.current.hata).toEqual({ kod: "ayarSinirDisi", alan: "frekans_hz" });
    expect(mockApi.uygula).toHaveBeenCalledWith({ frekans_hz: 9999 });
    mockApi.baslat.mockResolvedValue({ tamam: true, veri: {} });
    await act(async () => {
      ok = await result.current.baslat();
    });
    expect(ok).toBe(true);
    expect(result.current.hata).toBeNull();
    expect(mockApi.durum).toHaveBeenCalledTimes(3); // başarılı komut → durum tazelendi
    mockApi.durdur.mockResolvedValue({ tamam: false });
    await act(async () => {
      await result.current.durdur();
    });
    expect(result.current.hata).toBeNull(); // hatasız başarısızlık
    mockApi.durum.mockResolvedValue({ tamam: true, veri: { etkin: null } });
    await act(async () => {
      jest.advanceTimersByTime(1000);
    });
    expect(result.current.durum).toEqual({});
    mockApi.durum.mockResolvedValue({ tamam: false, hata: { kod: "surucuOldu", alan: "" } });
    await act(async () => {
      jest.advanceTimersByTime(1000);
    });
    expect(result.current.hata).toEqual({ kod: "surucuOldu", alan: "" });
    unmount();
  });

  it("söküldükten sonra gelen yanıt yazılmaz", async () => {
    let coz: (v: unknown) => void = () => {};
    mockApi.durum.mockReturnValue(new Promise((r) => (coz = r)));
    const { result, unmount } = renderHook(() => useModul());
    let komut: Promise<boolean> = Promise.resolve(true);
    let cozK: (v: unknown) => void = () => {};
    mockApi.baslat.mockReturnValue(new Promise((r) => (cozK = r)));
    act(() => {
      komut = result.current.baslat();
    });
    unmount();
    await act(async () => {
      coz({ tamam: true, veri: { surucu: { bobin: true } } });
      cozK({ tamam: false, hata: { kod: "x", alan: "" } });
      await komut;
    });
  });
});
