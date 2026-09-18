// Author: mertaygn, cglrgrkn
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
  // services/emergencyStop.ts bunu KULLANIR: bridge ucuna X-API-Key eklenmezse uzaktan (tünel)
  // erişimde acil durdurma birincil yolu her seferinde 401 alıp yedek yola düşüyordu.
  authHeaders: jest.fn(() => ({ "X-API-Key": "test-token" })),
}));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn(() => true) }));
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
    // 2026-08-09: sunucunun reddetme gerekçesini yakalamak için `onHttpError` eklendi
    // (503 "tıbbi kayıt DB'si açılamadı" mesajı kullanıcıya AYNEN gösterilsin).
    expect.objectContaining({ onHttpError: expect.any(Function) }),
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

it("KRİTİK [2.tur 1.1]: status success ama hardware_stop_unconfirmed dolu → UYARI + seans yine kapanır", async () => {
  // Backend artık (denetim 2. tur) seans kaydını kapatıp donanım STOP'u DOĞRULANAMAYAN bobinleri
  // ayrı alanda bildiriyor: eskiden /session/stop koşulsuz "success" döndüğü için buradaki
  // "Durdurma onaylanamadı" uyarısı broker-ölü senaryosunda HİÇ tetiklenemiyordu.
  mockApiPost.mockResolvedValueOnce({ status: "success", session: {} }); // start
  mockApiPost.mockResolvedValueOnce({ status: "success", hardware_stop_unconfirmed: [6, 7] }); // stop
  const { result } = renderHook(() => useSessionControl());
  await act(async () => {
    await result.current.startSession(START);
  });

  let ret: boolean | undefined;
  await act(async () => {
    ret = await result.current.stopSession();
  });

  expect(mockAlert).toHaveBeenCalled();
  const [baslik, govde] = mockAlert.mock.calls[0] as [string, string];
  expect(baslik).toContain("Durdurma onaylanamadı");
  expect(govde).toContain("6, 7"); // hangi bobinler olduğu operatöre AÇIKÇA söylenir
  // Seans kaydı backend'de GERÇEKTEN kapandı → UI aktif göstermeye devam ETMEZ (null'dan farkı bu).
  expect(ret).toBe(true);
  expect(result.current.isActive).toBe(false);
});

it("KARŞIT-KANIT [2.tur 1.1]: teyitli success'te (alan yok) uyarı ÇIKMAZ", async () => {
  mockApiPost.mockResolvedValueOnce({ status: "success", session: {} }); // start
  mockApiPost.mockResolvedValueOnce({ status: "success" }); // stop — mutlu yol
  const { result } = renderHook(() => useSessionControl());
  await act(async () => {
    await result.current.startSession(START);
  });
  await act(async () => {
    await result.current.stopSession();
  });

  expect(mockAlert).not.toHaveBeenCalled();
});

// ── emergencyStop ────────────────────────────────────────────────────────────
it("emergencyStop backend'ce TEYİT edildi → uyarı YOK, state reset", async () => {
  // ⚠️ 2026-08-09: eski hâli `{ stmStopped: true, mqttResults: [] }` gönderiyordu ve bunu teyit
  // sayıyordu. Boş `mqttResults` "ESP doğrulanmadı" demektir (backend bunu fail-closed yorumlar,
  // bkz. api_server._emergency_stop_all) — yani bu test, kapatılan yalanın ta kendisini
  // sözleşme olarak kilitliyordu. Artık teyit TEK kaynaktan: backend'in `confirmed` alanı.
  (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      status: "success", confirmed: true, stmStopped: true,
      mqttResults: [{ mqtt: "success" }, { mqtt: "success" }, { mqtt: "success" }],
    }),
  });
  const { result } = renderHook(() => useSessionControl());

  await act(async () => {
    await result.current.emergencyStop();
  });

  expect(mockAlert).not.toHaveBeenCalled();
  expect(result.current.isActive).toBe(false);
  expect(result.current.elapsedSec).toBe(0);
  // REGRESYON KİLİDİ: acil durdurma isteği KİMLİK BİLGİSİYLE gitmeli. Header'sız gönderilirse
  // uzaktan erişimde 401 alınır ve durdurma ancak saniyeler sonra yedek yoldan gerçekleşir.
  const [, init] = (global as unknown as { fetch: jest.Mock }).fetch.mock.calls[0];
  expect((init.headers as Record<string, string>)["X-API-Key"]).toBe("test-token");
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

// ── zamanlayıcı yolları (güvenlik-kritik, önceden TESTSİZ) ───────────────────
it("süre dolunca seans otomatik kapanır (remaining=0 → isActive false)", async () => {
  mockApiPost.mockResolvedValue({ status: "success", session: {} });
  // 2sn'lik mutabakat backend'i "seans sürüyor" desin; testin konusu YEREL sayaç.
  mockApiGet.mockResolvedValue({ is_active: true, duration_minutes: 1 });
  const { result } = renderHook(() => useSessionControl());
  await act(async () => {
    await result.current.startSession({ ...START, durationMinutes: 1 }); // 60 sn
  });
  expect(result.current.isActive).toBe(true);

  await act(async () => { jest.advanceTimersByTime(59_000); });
  expect(result.current.isActive).toBe(true);   // daha bitmedi
  expect(result.current.remainingSec).toBe(1);

  await act(async () => { jest.advanceTimersByTime(1_000); });
  expect(result.current.remainingSec).toBe(0);
  expect(result.current.isActive).toBe(false);
});

it("KRİTİK: SÜRESİZ seans (0 dk) kendini ~1sn'de BİTİRMEZ — UI çalışan tedaviye kör kalmaz", async () => {
  mockApiPost.mockResolvedValue({ status: "success", session: {} });
  mockApiGet.mockResolvedValue({ is_active: true, duration_minutes: 0 });
  const { result } = renderHook(() => useSessionControl());
  await act(async () => {
    await result.current.startSession({ ...START, durationMinutes: 0 });
  });
  await act(async () => { jest.advanceTimersByTime(5_000); });
  expect(result.current.isActive).toBe(true);      // hâlâ aktif (otomatik bitiş YOK)
  expect(result.current.elapsedSec).toBe(5);       // yalnız geçen süre sayılır
});

// REGRESYON: /session/active BOŞ 2xx gövdesi dönerse apiGet ÇAĞIRANIN fallback'ini (null) vermeli.
// Eskiden parseJsonSafe sabit `{}` döndürüyordu → `!sess.is_active` doğru çıkıp mutabakat, seansı
// UI'da BİTMİŞ gösteriyordu; bobinler sürerken kart "Tedavi Bekleniyor" diyordu.
it("KRİTİK: mutabakat yanıtı yoksa (null) yerel sayaç DEVAM eder, seans kapanmaz", async () => {
  mockApiPost.mockResolvedValue({ status: "success", session: {} });
  const { result } = renderHook(() => useSessionControl());
  await act(async () => {
    await result.current.startSession({ ...START, durationMinutes: 20 });
  });
  mockApiGet.mockResolvedValue(null); // bağlantı yok / boş gövde → fallback
  await act(async () => { jest.advanceTimersByTime(6_000); });
  expect(result.current.isActive).toBe(true);
});

it("mutabakat: backend seansı bitirdiyse (is_active=false) UI kapanır", async () => {
  mockApiPost.mockResolvedValue({ status: "success", session: {} });
  const { result } = renderHook(() => useSessionControl());
  await act(async () => {
    await result.current.startSession({ ...START, durationMinutes: 20 });
  });
  expect(result.current.isActive).toBe(true);

  mockApiGet.mockResolvedValue({ is_active: false }); // backend/başka istemci durdurdu
  await act(async () => { jest.advanceTimersByTime(2_000); }); // reconcile aralığı
  await waitFor(() => expect(result.current.isActive).toBe(false));
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

/**
 * ⚠️ HASTA GÜVENLİĞİ (2026-08-09 denetimi) — KISMİ DURDURMA "BAŞARILI" SAYILMAZ.
 * Kabuk-seviyesindeki uyarı, `performEmergencyStop`'un teyidine bağlıdır. Kısmi durdurma teyit
 * sayılırsa operatör "kesildi" görür, seans ekranı kapanır ve hâlâ enerjili bir bobin GÖZDEN KAÇAR.
 */
it("KRİTİK: STM durdu ama ESP durmadı (partial) → 'DOĞRULANAMADI' uyarısı ÇIKAR", async () => {
  (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      status: "partial", confirmed: false, stmStopped: true,
      mqttResults: [{ mqtt: "mqtt_unavailable" }, { mqtt: "mqtt_unavailable" }, { mqtt: "mqtt_unavailable" }],
    }),
  });
  mockApiPost.mockResolvedValue(null);          // yedek yollar da teyit veremiyor
  const { result } = renderHook(() => useSessionControl());

  await act(async () => {
    await result.current.emergencyStop();
  });

  expect(mockAlert).toHaveBeenCalled();
  const [title] = mockAlert.mock.calls[mockAlert.mock.calls.length - 1];
  expect(String(title)).toContain("DOĞRULANAMADI");
});

/**
 * ⚠️ KAYITSIZ TEDAVİ KAPISI (2026-08-09) — SUNUCUNUN GEREKÇESİ EKRANA ÇIKMALI.
 * Backend, tıbbi kayıt DB'si açılamadığında 503 + açıklayıcı `detail` döner. İstemci bunu yutup
 * "Seans başlatılamadı." derse veteriner hasta masadayken sebebi ANLAYAMAZ ve düzeltemez.
 */
it("KRİTİK: 503 (DB hazır değil) → sunucunun gerekçesi kullanıcıya gösterilir", async () => {
  const gerekce = "Tıbbi kayıt veritabanı açılamadı; seans başlatılamaz.";
  mockApiPost.mockImplementation(async (_yol, _govde, varsayilan, opt) => {
    (opt as { onHttpError?: (s: number, d?: string) => void })?.onHttpError?.(503, gerekce);
    return varsayilan;
  });
  const { result } = renderHook(() => useSessionControl());

  let ret: boolean | undefined;
  await act(async () => { ret = await result.current.startSession(START); });

  expect(ret).toBe(false);
  expect(result.current.isActive).toBe(false);       // kayıtsız tedavi BAŞLAMAZ
  expect(result.current.error).toBe(gerekce);
});

it("gerekçe yoksa genel mesaja düşer (davranış korunur)", async () => {
  mockApiPost.mockResolvedValue(null);
  const { result } = renderHook(() => useSessionControl());
  await act(async () => { await result.current.startSession(START); });
  expect(result.current.error).toBe("Seans başlatılamadı.");
});

// ── 409 SOZLESMESI (surum-kaymasi guvenlik sinyali, 2026-08-22) ──────────────
// Backend, donanim STOP'u dogrulanamayan bobin varsa artik 2xx DEGIL 409 doner (eski istemci
// yeni bir ALANI yutabilir ama 2xx-disini yutamaz). Bu istemci 409'u AYIRT ETMELI:
// seans kaydi GERCEKTEN kapandi (session_closed) -> UI seansi kapatir + bobin listesi uyarisi.

it("stopSession 409: seans kapanir + teyitsiz bobin listesi uyarisi cikar", async () => {
  mockApiPost.mockResolvedValue({ status: "success", session: {} });
  const { result } = renderHook(() => useSessionControl());
  await act(async () => {
    await result.current.startSession(START);
  });

  // 409 yolu: apiPost null doner + onHttpError(409, detail, govde) cagirir.
  mockApiPost.mockImplementation(async (_p: string, _b: unknown, fallback: unknown, opts?: {
    onHttpError?: (k: number, d?: string, g?: unknown) => void;
  }) => {
    opts?.onHttpError?.(409, "ACIL DURDUR'a basin", {
      hardware_stop_unconfirmed: [6, 7],
      session_closed: true,
    });
    return fallback;
  });

  let ret: boolean | undefined;
  await act(async () => {
    ret = await result.current.stopSession();
  });

  expect(ret).toBe(true); // seans kaydi kapandi -> UI kapanmali (genel-hata sanilmamali)
  expect(result.current.isActive).toBe(false);
  const uyarilar = mockAlert.mock.calls.map((c) => String(c[1]));
  expect(uyarilar.some((m) => m.includes("6") && m.includes("7"))).toBe(true);
  expect(uyarilar.some((m) => m.toUpperCase().includes("ACİL DURDUR"))).toBe(true);
});

it("KARSIT-KANIT stopSession null (ag yok): seans ACIK kalir + genel uyari (409'dan farkli)", async () => {
  mockApiPost.mockResolvedValue({ status: "success", session: {} });
  const { result } = renderHook(() => useSessionControl());
  await act(async () => {
    await result.current.startSession(START);
  });

  mockApiPost.mockImplementation(async (_p: string, _b: unknown, fallback: unknown) => fallback);

  let ret: boolean | undefined;
  await act(async () => {
    ret = await result.current.stopSession();
  });

  expect(ret).toBe(false); // sunucuya ULASILAMADI: kayit kapanmadi, seans acik kalmali
  expect(result.current.isActive).toBe(true);
});
