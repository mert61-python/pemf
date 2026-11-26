// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 (kapanış İngilizce taraması) · Seans DEĞERLERİ gösterimde değer → anahtar.
 *
 * `mode` ("Manuel" | "Otomatik" | "AI") ve `target_condition` (`AUTO_TARGETS`) seansa / DB'ye giden VERİdir ve Türkçe kalır; ekrana
 * basılırken çevrilir (geçmiş kartı, seans detayı, aktif seans kartı, ana ekran, KPI mod dağılımı). TR görünüm eskisiyle BAYT BAYT aynı;
 * bilinmeyen değer (serbest metin, eski kayıt, "AI") AYNEN. ⚠️ Beklenen metinler BURADA sabittir (üründen okunmaz).
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});

let mockSeanslar: unknown = [];
let mockDetay: unknown = null;
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) => (/\/details$/.test(yol) ? mockDetay : mockSeanslar)),
  apiPost: jest.fn(async () => ({ status: "success" })),
  platformConfirm: jest.fn(async () => false),
  platformAlert: jest.fn(),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/AppNavContext", () => ({ useAppNav: () => ({ selectedPatient: null }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperatorOptional: () => ({ operatorEmail: "a@x.com", operators: [], kimlikDbOkunamiyor: false }),
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ isExpert: false, isResearcher: false }) }));
jest.mock("@/services/dosyaIndir", () => ({ downloadFileWithAuth: jest.fn() }));
jest.mock("@/services/backendKonumu", () => ({ backendBuMakinede: () => false }));
jest.mock("expo-file-system/legacy", () => ({ cacheDirectory: "file:///", downloadAsync: jest.fn(), deleteAsync: jest.fn() }));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));

import { readFileSync } from "fs";
import { join } from "path";
import { act, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";
import React from "react";

import { SessionDetailModal } from "@/components/domain/SessionDetailModal";
import { SessionProgressCard } from "@/components/domain/SessionProgressCard";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";
import { hedefEtiketi, modEtiketi } from "@/utils/seansDegerEtiketi";

const depo = { setItem: async () => undefined };

/** [ham değer (DB / istek), TR görünüm, EN görünüm] */
const HEDEFLER: [string, string, string][] = [
  ["Doku İyileşmesi", "Doku İyileşmesi", "Tissue Healing"],
  ["Eklem Ağrısı", "Eklem Ağrısı", "Joint Pain"],
  ["Kas Spazmı", "Kas Spazmı", "Muscle Spasm"],
  ["Kırık İyileşmesi", "Kırık İyileşmesi", "Fracture Healing"],
  ["Enflamasyon Azaltma", "Enflamasyon Azaltma", "Inflammation Reduction"],
  ["Sinir Rejenerasyonu", "Sinir Rejenerasyonu", "Nerve Regeneration"],
  ["Bağ Dokusu Tamiri", "Bağ Dokusu Tamiri", "Connective Tissue Repair"],
  ["Ödem Azaltma", "Ödem Azaltma", "Edema Reduction"],
];
const MODLAR: [string, string, string][] = [
  ["Manuel", "Manuel", "Manual"],
  ["Otomatik", "Otomatik", "Automatic"],
  ["AI", "AI", "AI"],
];

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
const kaynak = (rel: string) => readFileSync(join(__dirname, "..", "..", rel), "utf8");

describe("hedefEtiketi / modEtiketi (birim)", () => {
  it("TR: her değer KENDİSİ (göç öncesiyle bayt bayt); bilinmeyen / serbest metin / boş AYNEN", () => {
    for (const [ham, tr] of HEDEFLER) expect(hedefEtiketi(i18n.t, ham)).toBe(tr);
    for (const [ham, tr] of MODLAR) expect(modEtiketi(i18n.t, ham)).toBe(tr);
    for (const serbest of ["Eklem", "Tümör modeli (DEMO)", "", "ödem azaltma"]) expect(hedefEtiketi(i18n.t, serbest)).toBe(serbest);
    for (const serbest of ["manual", "", "Manuel (eski)"]) expect(modEtiketi(i18n.t, serbest)).toBe(serbest);
  });

  it("EN: değer → İngilizce ad; bilinmeyen / serbest metin AYNEN (veri yutulmaz); 'AI' iki dilde aynı", async () => {
    await enYap();
    for (const [ham, , en] of HEDEFLER) expect(hedefEtiketi(i18n.t, ham)).toBe(en);
    for (const [ham, , en] of MODLAR) expect(modEtiketi(i18n.t, ham)).toBe(en);
    expect(hedefEtiketi(i18n.t, "Eklem")).toBe("Eklem");
    expect(modEtiketi(i18n.t, "manual")).toBe("manual");
    expect(hedefEtiketi(i18n.t, "")).toBe("");
  });
});

const KAYIT = (id: number, ek: Record<string, unknown> = {}) => ({
  id,
  patient_name: `Hasta${id}`,
  session_date: "2026-10-01",
  start_time: "10:00",
  session_status: "completed",
  operator_email: "a@x.com",
  treatment_mode: "Otomatik",
  target_condition: "Ödem Azaltma",
  duration_minutes: 20,
  frequency_hz: 10,
  intensity_mt: null,
  patient_notes: "",
  ...ek,
});

describe("TreatmentHistoryScreen kartı", () => {
  beforeEach(() => {
    mockSeanslar = [KAYIT(1, { patient_name: "Tekir" }), KAYIT(2, { treatment_mode: "Manuel", target_condition: "Eklem" })];
  });
  const ekran = async () => {
    const u = render(<TreatmentHistoryScreen />);
    await waitFor(() => expect(u.getAllByText(/Tekir/).length).toBeGreaterThan(0));
    return u;
  };

  it("TR: 'Otomatik' / 'Ödem Azaltma' / 'Manuel' / serbest 'Eklem' göç öncesiyle aynı", async () => {
    const u = await ekran();
    expect(u.getAllByText("Otomatik").length).toBe(1);
    expect(u.getAllByText("Ödem Azaltma").length).toBe(1);
    expect(u.getAllByText("Manuel").length).toBe(1);
    expect(u.getAllByText("Eklem").length).toBe(1);
  });

  it("EN: mod ve hedef İngilizce; serbest metin AYNEN; ham Türkçe değer ekranda KALMADI", async () => {
    await enYap();
    const u = await ekran();
    expect(u.getAllByText("Automatic").length).toBe(1);
    expect(u.getAllByText("Edema Reduction").length).toBe(1);
    expect(u.getAllByText("Manual").length).toBe(1);
    expect(u.getAllByText("Eklem").length).toBe(1); // serbest metin: çevrilmez
    for (const ham of ["Otomatik", "Ödem Azaltma", "Manuel"]) expect(u.queryByText(ham)).toBeNull();
  });
});

describe("SessionDetailModal", () => {
  const DETAY = {
    session: {
      id: 7,
      patient_name: "Tekir",
      session_date: "2026-10-01",
      start_time: "10:00",
      end_time: "10:20",
      duration_minutes: 20,
      treatment_mode: "Otomatik",
      target_condition: "Kırık İyileşmesi",
      operator_name: "Dr. A",
      session_status: "completed",
      patient_notes: "",
    },
    coil_runs: [],
    sensor_samples: [],
  };
  const ac = async () => {
    mockDetay = DETAY;
    const u = render(<SessionDetailModal visible sessionId={7} onClose={() => {}} />);
    await waitFor(() => expect(metin(u)).toContain("Tekir"));
    return u;
  };

  it("TR: mod / hedef göç öncesiyle aynı", async () => {
    const u = await ac();
    expect(u.getAllByText("Otomatik").length).toBe(1);
    expect(u.getAllByText("Kırık İyileşmesi").length).toBe(1);
  });

  it("EN: mod / hedef İngilizce", async () => {
    await enYap();
    const u = await ac();
    expect(u.getAllByText("Automatic").length).toBe(1);
    expect(u.getAllByText("Fracture Healing").length).toBe(1);
    expect(u.queryByText("Otomatik")).toBeNull();
    expect(u.queryByText("Kırık İyileşmesi")).toBeNull();
  });
});

describe("SessionProgressCard (aktif seans kartı)", () => {
  const temel = {
    isActive: true,
    elapsedSec: 60,
    remainingSec: 540,
    durationSec: 600,
    frequencyHz: 10,
    intensityMt: 1.5,
    onStop: jest.fn(),
    onEmergencyStop: jest.fn(),
  };
  it("TR: 'Manuel' / 'Otomatik' göç öncesiyle aynı; bilinmeyen değer AYNEN", () => {
    expect(render(<SessionProgressCard {...temel} mode="Manuel" />).getByText("Manuel")).toBeTruthy();
    expect(render(<SessionProgressCard {...temel} mode="Otomatik" />).getByText("Otomatik")).toBeTruthy();
    expect(render(<SessionProgressCard {...temel} mode="AI" />).getByText("AI")).toBeTruthy();
  });
  it("EN: 'Manual' / 'Automatic'; 'AI' aynı", async () => {
    await enYap();
    expect(render(<SessionProgressCard {...temel} mode="Manuel" />).getByText("Manual")).toBeTruthy();
    expect(render(<SessionProgressCard {...temel} mode="Otomatik" />).getByText("Automatic")).toBeTruthy();
    expect(render(<SessionProgressCard {...temel} mode="AI" />).getByText("AI")).toBeTruthy();
  });
});

describe("kaynak kapıları: ham mod / hedef değeri ekrana BASILMAZ", () => {
  it("Ana Ekran aktif seans kartı başlığı `modEtiketi` ile", () => {
    const k = kaynak("screens/DashboardScreen.tsx");
    expect(k).toContain("modEtiketi(t, at.mode)");
    expect(k).not.toMatch(/\(at\.mode \|\|/);
  });
  it("KPI mod dağılımı (pasta göstergesi adı) `modEtiketi` ile; ham anahtar etikete basılmaz", () => {
    const k = kaynak("screens/KpiDashboardScreen.tsx");
    expect(k).toContain("name: modEtiketi(t, name)");
  });
  it("Kontrol ekranı hedef çipi paylaşılan `hedefEtiketi`yi kullanır (yerel kopya YOK)", () => {
    const k = kaynak("screens/ControlScreen.tsx");
    expect(k).toContain('import { hedefEtiketi } from "@/utils/seansDegerEtiketi";');
    expect(k).toContain("{hedefEtiketi(t, hedef)}");
    expect(k).not.toMatch(/const hedefEtiketi\s*=/);
  });
  it("VERİ: seansa giden değerler (AUTO_TARGETS / mode) Türkçe KALIR — `targetCondition: autoTarget`, `mode: \"Manuel\"` dokunulmadı", () => {
    const k = kaynak("screens/ControlScreen.tsx");
    expect(k).toContain("targetCondition: autoTarget,");
    expect(k).toContain('mode: "Manuel",');
    expect(k).toContain('"Doku İyileşmesi", "Eklem Ağrısı", "Kas Spazmı"');
  });
});
