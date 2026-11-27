// Author: mertaygn, cglrgrkn
/**
 * YS2 a · B1 (YG0 25-11): kendiliğinden durdurulan AI Pro seansı geçmiş kartında ve seans detayında "Durduruldu (neden)" — backend
 * `session_parameters.durdurma_nedeni` kodundan (PDF / CSV ile AYNI kaynak ve etiket; `utils/seans_durum.DURDURMA_NEDENLERI`).
 * Bilinmeyen / boş neden eklenmez (yalın "Durduruldu"); nedeni olmayan seans AYNEN. ⚠️ Beklenen metinler BURADA sabittir.
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

import { act, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";
import React from "react";

import { SessionDetailModal } from "@/components/domain/SessionDetailModal";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";
import { nedenliDurum } from "@/utils/seansDegerEtiketi";

const depo = { setItem: async () => undefined };

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

const KAYIT = (id: number, ek: Record<string, unknown> = {}) => ({
  id,
  patient_name: `Hasta${id}`,
  session_date: "2026-11-25",
  start_time: "13:06",
  session_status: "stopped",
  operator_email: "a@x.com",
  treatment_mode: "AI Pro · Petri Kuyu · Kuyu D3",
  target_condition: "Kuyu D3",
  duration_minutes: 1,
  frequency_hz: 10,
  intensity_mt: 1.43,
  patient_notes: "",
  ...ek,
});

describe("nedenliDurum", () => {
  it("bilinen neden eklenir; bilinmeyen / boş / null neden EKLENMEZ", () => {
    expect(nedenliDurum(i18n.t, "Durduruldu", "plaka_kaydi")).toBe("Durduruldu (plaka kaydı)");
    expect(nedenliDurum(i18n.t, "Durduruldu", "plaka_dogrulanamadi")).toBe("Durduruldu (plaka doğrulanamadı)");
    expect(nedenliDurum(i18n.t, "Durduruldu", "hedef_kaybi")).toBe("Durduruldu (hedef kaybı)");
    for (const yok of [undefined, null, "", "uydurma"]) expect(nedenliDurum(i18n.t, "Durduruldu", yok)).toBe("Durduruldu");
  });
});

describe("TreatmentHistoryScreen kartı", () => {
  beforeEach(() => {
    mockSeanslar = [
      KAYIT(1, { patient_name: "Petri1256", durdurma_nedeni: "plaka_dogrulanamadi", intensity_mt: 0, duration_minutes: 0 }),
      KAYIT(2, { patient_name: "PetriT8", durdurma_nedeni: "plaka_kaydi" }),
      KAYIT(3, { patient_name: "Elle", durdurma_nedeni: null }),
    ];
  });
  const ekran = async () => {
    const u = render(<TreatmentHistoryScreen />);
    await waitFor(() => expect(u.getAllByText(/PetriT8/).length).toBeGreaterThan(0));
    return u;
  };

  it("TR: kart durumu 'Durduruldu (plaka doğrulanamadı)' / '(plaka kaydı)'; nedensiz seans yalın 'Durduruldu'", async () => {
    const u = await ekran();
    expect(u.getAllByText("Durduruldu (plaka doğrulanamadı)").length).toBe(1);
    expect(u.getAllByText("Durduruldu (plaka kaydı)").length).toBe(1);
    expect(u.getAllByText("Durduruldu").length).toBe(1);
  });

  it("EN: 'Stopped (plate not verified)' / 'Stopped (plate moved)'", async () => {
    await enYap();
    const u = await ekran();
    expect(u.getAllByText("Stopped (plate not verified)").length).toBe(1);
    expect(u.getAllByText("Stopped (plate moved)").length).toBe(1);
    expect(u.getAllByText("Stopped").length).toBe(1);
  });
});

describe("SessionDetailModal", () => {
  const ac = async (neden: string | null) => {
    mockDetay = {
      session: { ...KAYIT(7, { patient_name: "PetriT8" }), end_time: "13:09", operator_name: "Dr. A", durdurma_nedeni: neden },
      coil_runs: [],
      sensor_samples: [],
    };
    const u = render(<SessionDetailModal visible sessionId={7} onClose={() => {}} />);
    await waitFor(() => expect(u.getAllByText(/PetriT8/).length).toBeGreaterThan(0));
    return u;
  };

  it("TR: detay durumu 'Durduruldu (hedef kaybı)'", async () => {
    const u = await ac("hedef_kaybi");
    expect(u.getAllByText("Durduruldu (hedef kaybı)").length).toBe(1);
  });

  it("EN: 'Stopped (target lost)'; nedensiz yalın 'Stopped'", async () => {
    await enYap();
    expect((await ac("hedef_kaybi")).getAllByText("Stopped (target lost)").length).toBe(1);
    expect((await ac(null)).getAllByText("Stopped").length).toBe(1);
  });
});
