// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · AI geçmişi (AiHistoryScreen) ve KPI paneli (KpiDashboardScreen) iki dilde. TR göç öncesiyle BAYT BAYT aynı; EN doğru ve sade.
 * ⚠️ Beklenen metinler BURADA sabittir. VERİ: silme / değerlendirme istek gövdeleri ve dosya adları EN iken de TR ile aynıdır.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});

let mockKayitlar: unknown[] = [];
let mockKpi: unknown = null;
const mockApiPost = jest.fn(async (..._a: unknown[]): Promise<unknown> => ({ status: "success" }));
const mockIndir = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) => {
    if (yol.startsWith("/ai/log")) return { status: "success", data: mockKayitlar };
    if (yol.startsWith("/kpi/summary")) return mockKpi;
    return null;
  }),
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  platformConfirm: jest.fn(async () => false),
  platformAlert: jest.fn(),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
jest.mock("@/services/dosyaIndir", () => ({ downloadFileWithAuth: (...a: unknown[]) => mockIndir(...a), backendBuMakinede: () => false }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({ useOperatorOptional: () => ({ operatorEmail: "a@x.com", operators: [], kimlikDbOkunamiyor: false }) }));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian", isExpert: true, isResearcher: false }) }));
let mockSnap: any = { coils: [], system: {}, notifications: [], sessions: [] };
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnap, wsConnected: true, connectionQuality: "live", haveRealData: true, telemetryStale: false, sensorHistory: {}, unreadCount: 0 }),
}));

import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import React from "react";

import { AiHistoryScreen } from "@/screens/AiHistoryScreen";
import { KpiDashboardScreen } from "@/screens/KpiDashboardScreen";
import { platformConfirm } from "@/services/apiClient";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const KAYIT = (id: number, ek: Record<string, unknown> = {}) => ({
  id,
  created_at: "2026-10-01T10:00:00",
  mode: "veterinarian",
  module_id: "disease",
  module_label: "Hastalık Analizi",
  patient_name: "Tekir",
  operator_email: "a@x.com",
  input_type: "clinical",
  result_summary: "Kedi Astımı (%62)",
  result_detail: { top_1_class: "feline asthma", perCoil: [{ id: 1 }, { id: 2 }] },
  confidence: 0.62,
  ...ek,
});

beforeEach(() => {
  mockKayitlar = [KAYIT(1)];
  mockKpi = null;
  mockApiPost.mockClear();
  mockIndir.mockClear();
  (platformConfirm as jest.Mock).mockClear();
  mockSnap = { coils: [], system: {}, notifications: [], sessions: [] };
});
afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});
async function enYap() {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
}
function metin(u: ReturnType<typeof render>): string {
  const topla = (n: any): string => {
    if (n == null) return "";
    if (typeof n === "string") return n;
    if (Array.isArray(n)) return n.map(topla).join("|");
    return topla(n.children);
  };
  return topla(u.toJSON());
}
async function gecmis() {
  const u = render(<AiHistoryScreen />);
  await waitFor(() => expect(metin(u)).toContain("Hastalık Analizi"));
  return u;
}

describe("AiHistoryScreen", () => {
  it("TR: başlık çubuğu, kapsam düğmeleri, hasta / modül çipleri, kart ve açılan ayrıntı göç öncesiyle aynı", async () => {
    const u = await gecmis();
    let m = metin(u);
    for (const s of ["1 kayıt", "Geçmişi Sil", "Yenile", "Benim Analizlerim", "Tümü"]) expect(m).toContain(s);
    expect(u.getByLabelText("Kendi AI analiz geçmişimi sil")).toBeTruthy();
    expect(u.getByLabelText("Geçmişi yenile")).toBeTruthy();
    expect(u.getByLabelText("Benim analizlerim")).toBeTruthy();
    expect(u.getByLabelText("Tüm klinik analizleri")).toBeTruthy();
    const kart = u.getByLabelText("Hastalık Analizi kaydi");
    expect(kart.props.accessibilityHint).toBe("Ayrintilari acar");
    await act(async () => {
      fireEvent.press(kart);
    });
    m = metin(u);
    for (const s of ["Girdi tipi: Klinik değerler", "Güven: %62", "Kedi Astımı", "Bobin ayarları", "2 öğe", "Sonucu paylaş (PDF)", "Bu kaydı sil", "Veteriner"]) {
      expect(m).toContain(s);
    }
    expect(u.getByLabelText("Hastalık Analizi kaydi, acik").props.accessibilityHint).toBe("Ayrintilari kapatir");
    expect(u.getByLabelText("Hastalık Analizi sonucunu paylaş")).toBeTruthy();
    expect(u.getByLabelText("Hastalık Analizi kaydını sil")).toBeTruthy();
  });

  it("EN: aynı ekran İngilizce", async () => {
    await enYap();
    const u = await gecmis();
    let m = metin(u);
    for (const s of ["1 record", "Delete History", "Refresh", "My Analyses", "All"]) expect(m).toContain(s);
    expect(u.getByLabelText("Delete my AI analysis history")).toBeTruthy();
    expect(u.getByLabelText("Refresh history")).toBeTruthy();
    expect(u.getByLabelText("My analyses")).toBeTruthy();
    expect(u.getByLabelText("All clinic analyses")).toBeTruthy();
    const kart = u.getByLabelText("Hastalık Analizi record");
    expect(kart.props.accessibilityHint).toBe("Expands the details");
    await act(async () => {
      fireEvent.press(kart);
    });
    m = metin(u);
    for (const s of ["Input type: Clinical values", "Confidence: 62%", "Feline Asthma", "Coil settings", "2 items", "Share result (PDF)", "Delete this record"]) {
      expect(m).toContain(s);
    }
    expect(m).toMatch(/\|Vet(\||$)/); // profil rozeti kısa biçim (tam sözcük "Veteriner" DEĞİL)
    expect(u.getByLabelText("Hastalık Analizi record, expanded").props.accessibilityHint).toBe("Collapses the details");
    expect(u.getByLabelText("Share the result of Hastalık Analizi")).toBeTruthy();
    expect(u.getByLabelText("Delete the record of Hastalık Analizi")).toBeTruthy();
  });

  it("KRİTİK: tekil + toplu silme onayları iki dilde; onay verilmezse istek GİTMEZ; filtreli sayaç", async () => {
    const kos = async (kartEtiketi: string, silEtiketi: string, gecmisiSil: string) => {
      (platformConfirm as jest.Mock).mockClear();
      const u = await gecmis();
      await act(async () => {
        fireEvent.press(u.getByLabelText(kartEtiketi));
      });
      await act(async () => {
        fireEvent.press(u.getByLabelText(silEtiketi));
      });
      const tekil = (platformConfirm as jest.Mock).mock.calls.pop();
      await act(async () => {
        fireEvent.press(u.getByLabelText(gecmisiSil));
      });
      const toplu = (platformConfirm as jest.Mock).mock.calls.pop();
      u.unmount();
      return { tekil, toplu };
    };
    const tr = await kos("Hastalık Analizi kaydi", "Hastalık Analizi kaydını sil", "Kendi AI analiz geçmişimi sil");
    expect(tr.tekil).toEqual(["Kaydı sil", "Bu AI analiz kaydı kalıcı olarak silinecek. Bu işlem geri alınamaz."]);
    expect(tr.toplu).toEqual([
      "Geçmişi sil",
      "Kendi ve sahipsiz (eski) AI analiz kayıtlarınızın TAMAMI kalıcı olarak silinecek. Bu işlem geri alınamaz.\n\nHasta kayıtları ve seans geçmişi ETKİLENMEZ.",
    ]);
    expect(mockApiPost).not.toHaveBeenCalled();
    await enYap();
    const en = await kos("Hastalık Analizi record", "Delete the record of Hastalık Analizi", "Delete my AI analysis history");
    expect(en.tekil).toEqual(["Delete record", "This AI analysis record will be permanently deleted. This cannot be undone."]);
    expect(en.toplu).toEqual([
      "Delete history",
      "ALL of your own and ownerless (old) AI analysis records will be permanently deleted. This cannot be undone.\n\nPatient records and session history are NOT affected.",
    ]);
    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it("boş / hata / filtre iletileri iki dilde; çoğul sayaç (1 / 3 kayıt)", async () => {
    mockKayitlar = [];
    let u = render(<AiHistoryScreen />);
    await waitFor(() => expect(metin(u)).toContain("Henüz AI analiz kaydı yok. Akıllı Teşhis'ten bir analiz çalıştırın — sonuç burada şifreli, detaylı saklanır."));
    u.unmount();
    await enYap();
    u = render(<AiHistoryScreen />);
    await waitFor(() =>
      expect(metin(u)).toContain("There are no AI analysis records yet. Run an analysis from Smart Diagnosis — the result is stored here, encrypted and in detail."),
    );
    u.unmount();
    mockKayitlar = [KAYIT(1), KAYIT(2), KAYIT(3)];
    u = render(<AiHistoryScreen />);
    await waitFor(() => expect(metin(u)).toContain("3 records"));
  });

  it("VERİ: silme / değerlendirme istek yolları ve dosya adı EN iken de aynı (paylaş)", async () => {
    const kos = async (kartEtiketi: string, paylas: string) => {
      mockIndir.mockClear();
      const u = await gecmis();
      await act(async () => {
        fireEvent.press(u.getByLabelText(kartEtiketi));
      });
      await act(async () => {
        fireEvent.press(u.getByLabelText(paylas));
      });
      const c = mockIndir.mock.calls.map((x) => [x[0], x[1]]);
      u.unmount();
      return c;
    };
    const tr = await kos("Hastalık Analizi kaydi", "Hastalık Analizi sonucunu paylaş");
    expect(tr).toEqual([["http://127.0.0.1:8000/api/ai/log/1/pdf", "PEMF_AI_Tekir_1.pdf"]]);
    await enYap();
    expect(await kos("Hastalık Analizi record", "Share the result of Hastalık Analizi")).toEqual(tr);
  });
});

describe("KpiDashboardScreen", () => {
  const KPI = { totalSessions: 3, completedSessions: 2, stoppedSessions: 1, avgDurationMin: 12.4, modeDistribution: { Manuel: 2 }, last7Days: [{ date: "2026-10-01", count: 3 }] };
  const bobin = (id: number, ek: object = {}) => ({
    id, connected: true, running: true, frequencyHz: 100, dutyCycle: 40, magneticMt: 1.5, objectTemp: 40, ambientTemp: 20, currentA: 0,
    stm32Driven: true, measuredFields: ["magneticMt", "objectTemp"], akimGuvenilmez: false, ...ek,
  });
  const ac = async () => {
    mockKpi = KPI;
    mockSnap = { coils: [bobin(1), bobin(2)], system: {}, notifications: [], sessions: [], patient: { name: "" } };
    const u = render(<KpiDashboardScreen />);
    await waitFor(() => expect(metin(u)).toMatch(/12 (dk|min)/));
    return u;
  };

  it("TR: bölüm başlıkları, metrik etiketleri, birimler göç öncesiyle aynı", async () => {
    const m = metin(await ac());
    for (const s of [
      "Son 7 Gün — Seans Sayısı",
      "Toplam 3",
      "Seans Modu Dağılımı",
      "Toplam Seans",
      "Tamamlanma Oranı",
      "Ort. Süre",
      "12 dk",
      "Dur. / Hata",
      "⚡ Anlık Cihaz Durumu",
      "Bağlı Bobin",
      "Çalışan Bobin",
      "Cihaz Oranı",
      "Ort. Sıcaklık (2 bobin)",
      "Ort. Manyetik (2 bobin)",
      "📈 Performans Grafikleri",
      "🔬 Bobin Detayları",
    ]) {
      expect(m).toContain(s);
    }
  });

  it("EN: aynı panel İngilizce; çoğul 'coil(s)'; birim başlıkları aynı", async () => {
    await enYap();
    const m = metin(await ac());
    for (const s of [
      "Last 7 Days — Session Count",
      "Total 3",
      "Session Mode Distribution",
      "Total Sessions",
      "Completion Rate",
      "Avg. Duration",
      "12 min",
      "Stopped / Errors",
      "⚡ Live Device Status",
      "Running Coils",
      "Device Ratio",
      "Avg. Temperature (2 coils)",
      "Avg. Magnetic (2 coils)",
      "📈 Performance Charts",
      "🔬 Coil Details",
    ]) {
      expect(m).toContain(s);
    }
  });

  it("KRİTİK: ölçüm yokken SAHTE sayı yok — ölçüm yok / no measurement", async () => {
    mockKpi = KPI;
    mockSnap = { coils: [bobin(1, { objectTemp: 0, magneticMt: 0, measuredFields: [] })], system: {}, notifications: [], sessions: [] };
    let u = render(<KpiDashboardScreen />);
    await waitFor(() => expect(metin(u)).toContain("ölçüm yok"));
    expect(metin(u)).not.toContain("0.0 °C");
    u.unmount();
    await enYap();
    u = render(<KpiDashboardScreen />);
    await waitFor(() => expect(metin(u)).toContain("no measurement"));
    expect(metin(u)).not.toContain("0.0 °C");
  });
});
