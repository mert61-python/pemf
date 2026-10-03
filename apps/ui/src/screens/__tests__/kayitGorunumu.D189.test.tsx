// Author: mertaygn, cglrgrkn
/**
 * D1.89 · B-6.27 (+ İNCELEME-2 §10 #5 · İG-6.47 sınıfı) — reçete yoğunluğu "(kayıt)" etiketiyle, koşunun ÖLÇÜLEN alanı ayrı;
 * AI Pro'nun bobin 1 duty'si "mT" diye GÖSTERİLMEZ.
 * ====================================================================================================================
 * ÖLÇÜLEN KUSUR (06 §B-6.27, 06-2 §2; 1.9.50'de VAR): Geçmiş "Yoğunluk 1.5 mT", Seans Detayı "Şiddet 1.5 mT", Ana Ekran
 * "Yoğunluk 1.5 mT" — etiketsiz reçete; hekim cihazın uyguladığı alan sanıyordu (reçete STM/ESP'ye GÖNDERİLMEZ). Hiçbir
 * ekran koşunun ölçülen alanını (`summary.field_avg`) göstermiyordu. AI Pro'da Ana Ekran bobin 1 duty'sini "%30" yerine
 * "30 mT" gösteriyordu. Reçetesiz kayıt "0 mT" yazıyordu.
 *
 * Veri ELLE YAZILMADI: `__fixtures__/kayitGorunumu.D189.json` GERÇEK uçlardan üretilir (bayatlık kapısı
 * `tests/test_D189_kayit_gorunumu_RECETE_kayit_OLCULEN_ayri.py`): reçete 1,5 mT; bobin 1 alanı 0,8 mT ölçer, bobin 2 ÖLÇMEZ
 * (özet `field_avg: null`). GERÇEK: `TreatmentHistoryScreen`, `SessionDetailModal`, `DashboardScreen` + `LiveDataProvider`.
 * ⚠️ MUTASYON: herhangi bir görünümde "(kayıt)" etiketi kalkarsa, `field_avg` okunmazsa, ölçülmeyen alan 0 gösterilirse ya da
 * AI Pro duty'si yeniden mT okunursa KIRMIZI. Etiket render çıktısında aranır (yorumda değil).
 */
const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(async (_p: string, _b: unknown, fb: unknown) => fb),
  apiDelete: jest.fn(async () => null),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api", websocketUrl: "ws://127.0.0.1:8000/ws", apiToken: "" },
  loadStoredApiToken: jest.fn(async () => undefined),
}));
jest.mock("@/services/discovery", () => ({ discoverBackend: jest.fn(async () => null) }));
jest.mock("@/hooks/useNetworkReachability", () => ({ useNetworkReachability: () => undefined }));
jest.mock("@/hooks/useForegroundReconnect", () => ({ useForegroundReconnect: () => undefined }));
jest.mock("@/services/toastBridge", () => ({ emitToast: jest.fn() }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("@/hooks/useSessionControl", () => ({
  useSessionControl: () => ({
    isActive: false, treatment: null, elapsedSec: 0, remainingSec: 0,
    loading: false, stopping: false, error: null, lastError: () => null,
    startSession: jest.fn(), stopSession: jest.fn(), emergencyStop: jest.fn(),
  }),
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));
const mockWs: { onMessage?: (m: any) => void; onState?: (c: boolean) => void } = {};
jest.mock("@/services/wsClient", () => ({
  connectPemfWebSocket: (onMessage: any, onState: any) => {
    mockWs.onMessage = onMessage;
    mockWs.onState = onState;
    return () => undefined;
  },
}));

import React from "react";
import { act, render, waitFor, within } from "@testing-library/react-native";
import { LiveDataProvider } from "@/context/LiveDataContext";
import { DashboardScreen } from "@/screens/DashboardScreen";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { SessionDetailModal } from "@/components/domain/SessionDetailModal";

const F: any = require("./__fixtures__/kayitGorunumu.D189.json");

beforeEach(() => {
  mockApiGet.mockReset();
  mockApiGet.mockImplementation(async (yol: string, fb: unknown) => {
    if (yol.startsWith("/history/?")) return [F.listeOgesi];
    if (/^\/history\/\d+\/details/.test(yol)) return F.detay;
    return fb ?? null;
  });
});

async function anaEkran(at: any) {
  const u = render(
    <LiveDataProvider>
      <DashboardScreen />
    </LiveDataProvider>
  );
  await act(async () => {});
  await act(async () => {
    mockWs.onState?.(true);
  });
  await act(async () => {
    mockWs.onMessage?.({
      type: "snapshot",
      data: {
        stm: "online", gateway: "online", mqtt: "devre_disi", activeTreatment: at, notifications: [],
        coils: [1, 2, 3, 4, 5, 6, 7].map((id) => ({ id, connected: true, running: id <= 2 })),
      },
    });
  });
  return u;
}

describe("D1.89 — Ana Ekran (GERÇEK LiveDataProvider)", () => {
  it("KRİTİK: elle seansta ölçüm varken ÖLÇÜLEN gösterilir ve etiketi '(ölçülen)'", async () => {
    const u = await anaEkran(F.canliElle);
    // MetricCard'ın duyurulan metni "etiket: değer" (etiket düğümü erişilebilirlikten gizli) — ikisi BİRLİKTE aranır.
    expect(u.queryByLabelText("Yoğunluk (ölçülen): 0.80 mT")).not.toBeNull();
  });

  it("KRİTİK: ölçüm henüz yokken reçete '(kayıt)' etiketiyle (etiketsiz 'Yoğunluk' YOK)", async () => {
    // Seans başlarken backend ölçümü SIFIRLAR (`measuredIntensityMt: null`) — ilk telemetriden önceki gerçek hâl.
    const u = await anaEkran({ ...F.canliElle, measuredIntensityMt: null, measuredPeakMt: null });
    expect(u.queryByLabelText("Yoğunluk (kayıt): 1.5 mT")).not.toBeNull();
    expect(u.queryByLabelText(/^Yoğunluk: /)).toBeNull();
  });

  it("KRİTİK: AI Pro'da bobin 1 duty'si 'mT' DEĞİL — '%' ve duty etiketiyle", async () => {
    const duty = F.canliAiPro.dutyTemsilYuzde;
    expect(typeof duty).toBe("number"); // aparat: gerçek /frame duty temsilini yazdı
    const u = await anaEkran(F.canliAiPro);
    expect(u.queryByLabelText(new RegExp(`: ${duty} mT$`))).toBeNull();
    expect(u.queryByLabelText(`Duty (AI planı, bobin 1): %${duty}`)).not.toBeNull();
  });
});

describe("D1.89 — Tedavi Geçmişi (GERÇEK TreatmentHistoryScreen)", () => {
  it("KRİTİK: reçete '(kayıt)' etiketiyle gösterilir", async () => {
    const u = render(
      <LiveDataProvider>
        <TreatmentHistoryScreen />
      </LiveDataProvider>
    );
    await waitFor(() => expect(u.queryByText("Yoğunluk (kayıt)")).not.toBeNull());
    expect(u.queryByText("1.5 mT")).not.toBeNull();
  });

  it("KARŞIT: reçetesiz kayıt '0 mT' DEĞİL '—'", async () => {
    mockApiGet.mockImplementation(async (yol: string, fb: unknown) =>
      yol.startsWith("/history/?") ? [{ ...F.listeOgesi, intensity_mt: null }] : fb ?? null
    );
    const u = render(
      <LiveDataProvider>
        <TreatmentHistoryScreen />
      </LiveDataProvider>
    );
    await waitFor(() => expect(u.queryByText("Yoğunluk (kayıt)")).not.toBeNull());
    expect(u.queryByText("0 mT")).toBeNull();
  });
});

describe("D1.89 — Seans Detayı (GERÇEK SessionDetailModal)", () => {
  async function detay() {
    const u = render(<SessionDetailModal visible sessionId={1} onClose={() => {}} />);
    await waitFor(() => expect(u.queryByTestId("seans-bobin-satiri-1")).not.toBeNull());
    return u;
  }

  it("KRİTİK: reçete sütunu '(kayıt)', koşunun ölçülen alanı ayrı sütunda (bobin 1: 0.80 mT)", async () => {
    const u = await detay();
    expect(u.queryByText("Şiddet (kayıt)")).not.toBeNull();
    expect(u.queryByText("Alan (ölçülen)")).not.toBeNull();
    const satir1 = within(u.getByTestId("seans-bobin-satiri-1"));
    expect(satir1.queryByText("1.5 mT")).not.toBeNull();
    expect(u.getByTestId("seans-bobin-olculen-alan-1").props.children).toBe("0.80 mT");
  });

  it("KARŞIT: alanı ÖLÇMEYEN bobin 2 '0.00 mT' DEĞİL '—' (backend özeti null)", async () => {
    expect(F.detay.coil_runs.find((k: any) => k.coil_id === 2).summary.field_avg).toBeNull(); // aparat
    const u = await detay();
    expect(u.getByTestId("seans-bobin-olculen-alan-2").props.children).toBe("—");
  });

  it("KRİTİK D1.69 (Y6): dakika satırlarında sıcaklık ÖLÇÜLMEDİ (null) → grafik yerine 'sensör verisi yok' (0 °C çizgisi YOK)", async () => {
    // aparat: GERÇEK yanıt — bobin A yalnız alan, B yalnız akım ölçtü; sıcaklık hiç ölçülmedi (Y6: NULL, 0.0 DEĞİL).
    expect(F.detay.sensor_samples.length).toBeGreaterThan(0);
    expect(F.detay.sensor_samples.every((s: any) => s.temperature_c === null)).toBe(true);
    const u = await detay();
    expect(u.queryByText(/Bu seansta sensör verisi yok/)).not.toBeNull();
  });
});
