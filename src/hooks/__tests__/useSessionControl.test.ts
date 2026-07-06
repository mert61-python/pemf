/**
 * useSessionControl (audit B-3.2 kalan ekran-akış kilidi): güvenlik-kritik tedavi kontrol hook'u.
 * /api/session/start|stop + /hardware/emergency_stop iş mantığı. En kritik kilitler (audit P1):
 *   - stopSession backend-erişilemez → UYARI + false + seans AKTİF KALIR (yanlış 'durduruldu' YOK)
 *   - emergencyStop doğrulanamadı → "DOĞRULANAMADI" uyarısı (donanım hâlâ çalışıyor olabilir)
 * apiClient/config mock'lanır; fetch global mock. Bağlantı yok → UI donanımı durmuş GÖSTERMEMELİ.
 */
jest.mock("@/services/apiClient", () => ({
  apiPost: jest.fn(),
  apiGet: jest.fn(),
  platformAlert: jest.fn(),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { bridgeBaseUrl: "http://device.local/api" },
}));

import { renderHook, act, waitFor } from "@testing-library/react-native";
import { apiPost, apiGet, platformAlert } from "@/services/apiClient";
import { useSessionControl, type SessionStartParams } from "@/hooks/useSessionControl";

const mockApiPost = apiPost as jest.Mock;
const mockApiGet = apiGet as jest.Mock;
const mockAlert = platformAlert as jest.Mock;

const START: SessionStartParams = {
  mode: "Manuel",
  frequency: 50,
  duty: 25,
  intensity: 2,
  durationMinutes: 20,
};

beforeEach(() => {
  jest.useFakeTimers();
  mockApiPost.mockReset();
  mockApiGet.mockReset();
  mockAlert.mockReset();
  mockApiGet.mockResolvedValue({}); // mount: aktif seans yok (varsayılan)
  (global as { fetch: unknown }).fetch = jest.fn();
});
afterEach(() => {
  jest.useRealTimers();
});

// ── startSession ─────────────────────────────────────────────────────────────
it("startSession başarılı → isActive + treatment set, doğru payload, true döner", async () => {
  mockApiPost.mockResolvedValue({ status: "success", session: {} });
  const { result } = renderHook(() => useSessionControl());

  let ret: boolean | undefined;
  await act(async () => {
    ret = await result.current.startSession(START);
  });

  expect(ret).toBe(true);
  expect(result.current.isActive).toBe(true);
  expect(result.current.treatment?.mode).toBe("Manuel");
  expect(result.current.treatment?.durationSec).toBe(1200);
  expect(mockApiPost).toHaveBeenCalledWith(
    "/session/start",
    expect.objectContaining({ mode: "Manuel", duration_minutes: 20, frequency: 50 }),
    null,
  );
});

it("startSession başarısız (null yanıt) → error set, false, isActive KAPALI kalır", async () => {
  mockApiPost.mockResolvedValue(null);
  const { result } = renderHook(() => useSessionControl());

  let ret: boolean | undefined;
  await act(async () => {
    ret = await result.current.startSession(START);
  });

  expect(ret).toBe(false);
  expect(result.current.isActive).toBe(false);
  expect(result.current.error).toBeTruthy();
});

// ── stopSession ──────────────────────────────────────────────────────────────
it("stopSession onaylı (status ok) → isActive false, true döner", async () => {
  mockApiPost.mockResolvedValueOnce({ status: "success", session: {} }); // start
  mockApiPost.mockResolvedValueOnce({ status: "ok" }); // stop
  const { result } = renderHook(() => useSessionControl());
  await act(async () => {
    await result.current.startSession(START);
  });

  let ret: boolean | undefined;
  await act(async () => {
    ret = await result.current.stopSession();
  });

  expect(ret).toBe(true);
  expect(result.current.isActive).toBe(false);
});

it("KRİTİK: stopSession backend-erişilemez (null) → UYARI + false + seans AKTİF KALIR", async () => {
  mockApiPost.mockResolvedValueOnce({ status: "success", session: {} }); // start
  mockApiPost.mockResolvedValueOnce(null); // stop → sunucuya ulaşılamadı
  const { result } = renderHook(() => useSessionControl());
  await act(async () => {
    await result.current.startSession(START);
  });

  let ret: boolean | undefined;
  await act(async () => {
    ret = await result.current.stopSession();
  });

  expect(ret).toBe(false);
  expect(mockAlert).toHaveBeenCalled(); // "donanım HÂLÂ ÇALIŞIYOR olabilir" uyarısı
  // GÜVENLİK: STM'ye STOP ulaşmamış olabilir → UI seansı 'bitmiş' GÖSTERMEZ
  expect(result.current.isActive).toBe(true);
});

// ── emergencyStop ────────────────────────────────────────────────────────────
it("emergencyStop doğrulandı (stmStopped) → uyarı YOK, state reset", async () => {
  (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ stmStopped: true, mqttResults: [] }),
  });
  const { result } = renderHook(() => useSessionControl());

  await act(async () => {
    await result.current.emergencyStop();
  });

  expect(mockAlert).not.toHaveBeenCalled();
  expect(result.current.isActive).toBe(false);
  expect(result.current.elapsedSec).toBe(0);
});

it("KRİTİK: emergencyStop doğrulanamadı (bridge + fallback fail) → 'DOĞRULANAMADI' uyarısı", async () => {
  (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockRejectedValue(new Error("net"));
  mockApiPost.mockResolvedValue(null); // fallback stop_all_coils da doğrulanamaz
  const { result } = renderHook(() => useSessionControl());

  await act(async () => {
    await result.current.emergencyStop();
  });

  expect(mockAlert).toHaveBeenCalled();
  const [title] = mockAlert.mock.calls[mockAlert.mock.calls.length - 1];
  expect(String(title)).toContain("DOĞRULANAMADI");
});

// ── mount hidrasyonu ─────────────────────────────────────────────────────────
it("mount'ta backend'de aktif seans varsa state'i hidrate eder", async () => {
  mockApiGet.mockResolvedValue({
    is_active: true,
    duration_minutes: 20,
    elapsed_sec: 60,
    mode: "AI",
    frequency: 30,
    intensity: 1.5,
  });
  const { result } = renderHook(() => useSessionControl());

  await waitFor(() => expect(result.current.isActive).toBe(true));
  expect(result.current.treatment?.mode).toBe("AI");
  expect(result.current.elapsedSec).toBe(60);
});
