/**
 * KP-3 C · useSessionControl kapsanmayan kolları — her test bir DAVRANIŞ iddiası (useSessionControl.test düzeneğinin aynısı):
 *  - Mutabakat (2 sn'de bir /session/active): seans UZATILDIYSA toplam = geçen + kalan olur ve kalan süre sunucudan düzelir; benimsenen
 *    seansın DB satırı öğrenilir (gözlem notu oraya yazılır); bağlantı yoksa (istek düşer) yerel sayaç sürer; sunucu seansı bitirdiyse
 *    arayüz seansı kapatır ve mutabakat DURUR (artık istek yok).
 *  - Durdurma isteği istisna fırlatırsa false döner ve seans AÇIK kalır (yanlış "durduruldu" yok).
 *  - Başlatma isteği istisna fırlatırsa hatanın kendi iletisi (Error değilse genel ileti) gösterilir.
 * SAHTE: apiClient (ağ sınırı) · toast köprüsü · config.
 */
jest.mock("@/services/apiClient", () => ({
  apiPost: jest.fn(),
  apiGet: jest.fn(),
  platformAlert: jest.fn(),
  authHeaders: jest.fn(() => ({ "X-API-Key": "test-token" })),
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
jest.mock("@/services/config", () => ({ serviceConfig: { bridgeBaseUrl: "http://device.local/api" } }));

import { renderHook, act } from "@testing-library/react-native";
import i18n from "i18next";
import { apiPost, apiGet } from "@/services/apiClient";
import { useSessionControl, type SessionStartParams } from "@/hooks/useSessionControl";

const mockApiPost = apiPost as jest.Mock;
const mockApiGet = apiGet as jest.Mock;
const T = (k: string): string => (i18n.t as unknown as (k: string) => string)(k);
const AKTIF = { is_active: true, db_session_id: 41, duration_minutes: 10, elapsed_sec: 60, mode: "Manuel", frequency: 50, intensity: 1 };

beforeEach(() => {
  jest.useFakeTimers();
  mockApiPost.mockReset();
  mockApiGet.mockReset();
});
afterEach(() => jest.useRealTimers());

async function aktifSeansla() {
  mockApiGet.mockResolvedValueOnce(AKTIF);
  const h = renderHook(() => useSessionControl());
  await act(async () => { await Promise.resolve(); });
  expect(h.result.current.isActive).toBe(true);
  return h;
}
const ilerlet = async (ms: number) => { await act(async () => { jest.advanceTimersByTime(ms); await Promise.resolve(); await Promise.resolve(); }); };

it("uzatılan seansta toplam = geçen + kalan; DB satırı öğrenilir; bağlantı yoksa yerel sayaç sürer; bitince arayüz kapanır ve mutabakat DURUR", async () => {
  const h = await aktifSeansla();
  expect(h.result.current.dbSessionId).toBe(41);
  mockApiGet.mockResolvedValueOnce({ ...AKTIF, db_session_id: 42, elapsed_sec: 120, remaining_sec: 900 });
  await ilerlet(2000);
  expect(h.result.current.dbSessionId).toBe(42);
  expect(h.result.current.elapsedSec).toBe(120);
  expect(h.result.current.remainingSec).toBe(900); // 10 dk değil, uzatılmış toplam (120 + 900)
  mockApiGet.mockRejectedValueOnce(new Error("ağ yok"));
  await ilerlet(2000);
  expect(h.result.current.isActive).toBe(true); // bağlantı yok → seans kapanmaz
  mockApiGet.mockResolvedValueOnce({ is_active: false });
  await ilerlet(2000);
  expect(h.result.current.isActive).toBe(false);
  expect(h.result.current.treatment?.isActive).toBe(false);
  const sayi = mockApiGet.mock.calls.length;
  await ilerlet(10000);
  expect(mockApiGet.mock.calls.length).toBe(sayi); // mutabakat durdu
});

it("durdurma isteği istisna fırlatırsa false döner ve seans AÇIK kalır", async () => {
  const h = await aktifSeansla();
  mockApiPost.mockRejectedValueOnce(new Error("beklenmeyen"));
  let sonuc: boolean | undefined;
  await act(async () => { sonuc = await h.result.current.stopSession(); });
  expect(sonuc).toBe(false);
  expect(h.result.current.isActive).toBe(true);
});

it("başlatma isteği istisna fırlatırsa hatanın iletisi; Error değilse genel ileti", async () => {
  mockApiGet.mockResolvedValue({});
  const h = renderHook(() => useSessionControl());
  await act(async () => { await Promise.resolve(); });
  const P: SessionStartParams = { mode: "Manuel", frequency: 50, duty: 25, intensity: 2, durationMinutes: 20 };
  mockApiPost.mockRejectedValueOnce(new Error("Port meşgul"));
  await act(async () => { await h.result.current.startSession(P); });
  expect(h.result.current.error).toBe("Port meşgul");
  mockApiPost.mockRejectedValueOnce("dize-ret");
  await act(async () => { await h.result.current.startSession(P); });
  expect(h.result.current.error).toBe(T("seans.denetim.hataOlustu"));
});
