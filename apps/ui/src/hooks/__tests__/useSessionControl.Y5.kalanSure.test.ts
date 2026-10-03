// Author: mertaygn, cglrgrkn
/**
 * D1.70 · sahip kararı Y5 — seans ORTASINDA girilen süre KALAN süredir; backend seansın bitişini ona göre taşır
 * (`/api/session/parametre_guncelle` → `bitis_mono`; `/api/session/active.remaining_sec` yeni bitişten).
 *
 * ÖLÇÜLEN KUSUR: yerel sayaç toplam süreyi seans BAŞINDA kapanışta sabitliyordu ve mutabakat yalnız geçen süreyi
 * alıyordu → UZATMADA sayaç ESKİ bitişte 0'a inip seansı yerelde "bitti" sayıyor (mutabakat da duruyor), bobinler
 * sürerken kart "bitti" diyordu; KISALTMADA kalan süre eski toplamdan gösteriliyordu.
 */
jest.mock("@/services/apiClient", () => ({
  apiPost: jest.fn(),
  apiGet: jest.fn(),
  platformAlert: jest.fn(),
  authHeaders: jest.fn(() => ({ "X-API-Key": "test-token" })),
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("@/services/config", () => ({
  serviceConfig: { bridgeBaseUrl: "http://device.local/api" },
}));

import { renderHook, act } from "@testing-library/react-native";
import { apiPost, apiGet } from "@/services/apiClient";
import { useSessionControl, type SessionStartParams } from "@/hooks/useSessionControl";

const mockApiPost = apiPost as jest.Mock;
const mockApiGet = apiGet as jest.Mock;

const START: SessionStartParams = { mode: "Manuel", frequency: 100, duty: 40, intensity: 0, durationMinutes: 20 };

let t0 = 0;
let bitisSn = 1200; // backend'in kesin bitişi (seans başından saniye)
const gecen = () => Math.floor((Date.now() - t0) / 1000);

beforeEach(() => {
  jest.useFakeTimers();
  mockApiPost.mockReset();
  mockApiGet.mockReset();
  mockApiPost.mockResolvedValue({ status: "success", session: {} });
  // Backend mutabakatı: geçen süre + YENİ bitişten kalan süre (sunucunun `/session/active` sözleşmesi).
  mockApiGet.mockImplementation((yol: string) =>
    Promise.resolve(
      yol === "/session/active" && t0 > 0
        ? { is_active: gecen() < bitisSn, elapsed_sec: gecen(), remaining_sec: Math.max(0, bitisSn - gecen()) }
        : {},
    ),
  );
  t0 = 0;
  bitisSn = 1200;
});
afterEach(() => {
  jest.useRealTimers();
});

/** Mutabakat (2 sn) yanıtları ARADA işlensin diye adım adım ilerlet (tek dev adımda sahte zamanlayıcı tüm turları
 *  sözler çözülmeden koşturur — gerçekte yanıtlar 2 sn'de bir işlenir). */
async function ilerle(ms: number) {
  for (let kalan = ms; kalan > 0; kalan -= 2_000) {
    await act(async () => { jest.advanceTimersByTime(Math.min(2_000, kalan)); });
  }
}

async function baslat() {
  const r = renderHook(() => useSessionControl());
  await act(async () => {
    await r.result.current.startSession(START);
  });
  t0 = Date.now();
  return r;
}

it("KRİTİK Y5 UZATMA: 10. dk'da 15 dk kalan girilince yerel sayaç ESKİ bitişte (20. dk) seansı BİTİRMEZ", async () => {
  const { result } = await baslat();
  await ilerle(600_000);
  bitisSn = 600 + 900; // operatör 10. dk'da "15 dk" girdi → backend bitişi 25. dk
  await ilerle(610_000); // 20. dk + 10 sn
  expect(result.current.isActive).toBe(true);
  expect(Math.abs(result.current.remainingSec - 290)).toBeLessThanOrEqual(3);
});

it("KRİTİK Y5 KISALTMA: 10. dk'da 5 dk kalan girilince kalan süre YENİ bitişten gösterilir", async () => {
  const { result } = await baslat();
  await ilerle(600_000);
  bitisSn = 600 + 300; // backend bitişi 15. dk
  await ilerle(4_000);
  expect(result.current.isActive).toBe(true);
  expect(Math.abs(result.current.remainingSec - 296)).toBeLessThanOrEqual(3);
});

it("KARŞIT: süre değişmezse (backend kalan = toplam − geçen) sayaç planlanan sürede biter", async () => {
  const { result } = await baslat();
  await ilerle(1_194_000);
  expect(result.current.isActive).toBe(true);
  await ilerle(8_000);
  expect(result.current.isActive).toBe(false);
});
