// Author: mertaygn, cglrgrkn
/**
 * YS2 e · B8 (YG2 25-11, sahip isteği): Hastalar listesinde ve Seans Geçmişi'nde TOPLAM sayı — "2 hasta" / "20 seans"; süzgeç / arama
 * varsa "x / y gösteriliyor". Toplam profilin kümesidir (sunucu `X-PEMF-Profil` süzgeci): geçmişte istatistik ucundan (liste sayfalı),
 * hastalarda yüklü listeden. TR + EN (telefon aynı arayüz). ⚠️ Beklenen metinler BURADA sabittir.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});

const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(async () => ({ status: "success" })),
  platformConfirm: jest.fn(async () => false),
  platformAlert: jest.fn(),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/context/AppNavContext", () => ({
  useAppNav: () => ({ selectedPatient: null, navigateTo: jest.fn(), setSelectedPatient: jest.fn() }),
}));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
let mockOpEposta = "a@x.com";
jest.mock("@/context/OperatorContext", () => ({
  useOperatorOptional: () => ({ operatorEmail: mockOpEposta, operators: [], kimlikDbOkunamiyor: false }),
}));
let mockKip: { userMode: string; isExpert: boolean; isResearcher: boolean } = { userMode: "veterinarian", isExpert: true, isResearcher: false };
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => mockKip }));
jest.mock("@/services/dosyaIndir", () => ({ downloadFileWithAuth: jest.fn() }));
jest.mock("@/services/backendKonumu", () => ({ backendBuMakinede: () => false }));
jest.mock("@/services/desktopSession", () => ({ isDesktopHost: () => true }));
jest.mock("expo-file-system/legacy", () => ({ cacheDirectory: "file:///", downloadAsync: jest.fn(), deleteAsync: jest.fn() }));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));

import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import React from "react";

import { PatientScreen } from "@/screens/PatientScreen";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";
import { profilSozlugu } from "@/utils/profilSozlugu";

const depo = { setItem: async () => undefined };

afterEach(async () => {
  mockOpEposta = "a@x.com";
  mockKip = { userMode: "veterinarian", isExpert: true, isResearcher: false };
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

const SEANS = (id: number, ad: string) => ({
  id, patient_name: ad, session_date: "2026-11-25", start_time: "10:00", session_status: "completed", operator_email: "a@x.com",
  treatment_mode: "Manuel", target_condition: "", duration_minutes: 5, frequency_hz: 10, intensity_mt: null, patient_notes: "",
});
const HASTA = (id: string, ad: string) => ({
  id, name: ad, species: "Kedi", breed: "", age: "3", weight: "4", owner: "", vet_contact: "", owner_email: "", operator_email: "a@x.com",
});

function gecmisApi(toplam: number | null, liste: unknown[] = [SEANS(1, "Tekir"), SEANS(2, "Pamuk")]) {
  mockApiGet.mockReset();
  mockApiGet.mockImplementation(async (yol: string) =>
    yol === "/history/statistics" ? (toplam == null ? null : { total_sessions: toplam }) : liste,
  );
}
async function gecmis() {
  const u = render(<TreatmentHistoryScreen />);
  await waitFor(() => expect(u.getAllByText(/Tekir/).length).toBeGreaterThan(0));
  return u;
}

describe("Seans Geçmişi toplamı", () => {
  it("TR: süzgeçsiz '2 seans'; aramayla '1 / 2 seans gösteriliyor'", async () => {
    gecmisApi(2);
    const u = await gecmis();
    expect(u.getByTestId("gecmis-sayac").props.children).toBe("2 seans");
    await act(async () => { fireEvent.changeText(u.getByPlaceholderText(profilSozlugu({ researcher: false }).gecmisAraYer), "Tek"); });
    expect(u.getByTestId("gecmis-sayac").props.children).toBe("1 / 2 seans gösteriliyor");
  });

  it("TR: liste SAYFALIYSA toplam istatistik ucundan (profilin kümesi) — '50 / 120 seans gösteriliyor'", async () => {
    gecmisApi(120, Array.from({ length: 50 }, (_, i) => SEANS(i + 1, i === 0 ? "Tekir" : `Hasta${i}`)));
    const u = await gecmis();
    await waitFor(() => expect(u.getByTestId("gecmis-sayac").props.children).toBe("50 / 120 seans gösteriliyor"));
    expect(mockApiGet.mock.calls.map((c) => c[0])).toEqual(["/history/?limit=50", "/history/statistics"]); // liste ÖNCE
  });

  it("liste TAMSA istatistik ucu ÇAĞRILMAZ (toplam = liste)", async () => {
    gecmisApi(999);
    const u = await gecmis();
    expect(u.getByTestId("gecmis-sayac").props.children).toBe("2 seans");
    expect(mockApiGet.mock.calls.map((c) => c[0])).not.toContain("/history/statistics");
  });

  it("istatistik okunamazsa liste TAMAMSA yüklenen sayı yazılır", async () => {
    gecmisApi(null);
    const u = await gecmis();
    expect(u.getByTestId("gecmis-sayac").props.children).toBe("2 seans");
  });

  it("istatistik okunamaz ve liste SAYFALI (daha fazlası var) → sayı UYDURULMAZ (sayaç yok)", async () => {
    gecmisApi(null, Array.from({ length: 50 }, (_, i) => SEANS(i + 1, i === 0 ? "Tekir" : `Hasta${i}`)));
    const u = await gecmis();
    expect(u.queryByTestId("gecmis-sayac")).toBeNull();
  });

  it("kimliksiz (kayıt gösterilmez, Y103) → sayaç da yok", async () => {
    mockOpEposta = "";
    gecmisApi(2);
    const u = render(<TreatmentHistoryScreen />);
    await act(async () => {});
    expect(u.queryByTestId("gecmis-sayac")).toBeNull();
  });

  it("EN: '2 sessions' / 'Showing 1 of 2 sessions'", async () => {
    await enYap();
    gecmisApi(2);
    const u = await gecmis();
    expect(u.getByTestId("gecmis-sayac").props.children).toBe("2 sessions");
    await act(async () => { fireEvent.changeText(u.getByPlaceholderText(profilSozlugu({ researcher: false }).gecmisAraYer), "Tek"); });
    expect(u.getByTestId("gecmis-sayac").props.children).toBe("Showing 1 of 2 sessions");
  });
});

async function hastalar(liste: unknown[]) {
  mockApiGet.mockImplementation(async (yol: string) => (yol === "/patients" ? { status: "success", data: liste } : { status: "success", data: [] }));
  const u = render(<PatientScreen />);
  await act(async () => {});
  return u;
}

describe("Hastalar toplamı", () => {
  it("TR veteriner: '2 hasta'; aramayla '1 / 2 hasta gösteriliyor'", async () => {
    const u = await hastalar([HASTA("p1", "Boncuk"), HASTA("p2", "Zeytin")]);
    expect(u.getByTestId("hasta-sayac").props.children).toBe("2 hasta");
    const SK = profilSozlugu({ petOwner: false, researcher: false });
    await act(async () => { fireEvent.changeText(u.getByPlaceholderText(SK.araYer), "Bon"); });
    expect(u.getByTestId("hasta-sayac").props.children).toBe("1 / 2 hasta gösteriliyor");
  });

  it("TR araştırma: '1 örnek'", async () => {
    mockKip = { userMode: "researcher", isExpert: false, isResearcher: true };
    const u = await hastalar([HASTA("p1", "Fantom-1")]);
    expect(u.getByTestId("hasta-sayac").props.children).toBe("1 örnek");
  });

  it("TR araştırma + arama: '1 / 2 örnek gösteriliyor'", async () => {
    mockKip = { userMode: "researcher", isExpert: false, isResearcher: true };
    const u = await hastalar([HASTA("p1", "Fantom-1"), HASTA("p2", "Petri-2")]);
    const SK = profilSozlugu({ petOwner: false, researcher: true });
    await act(async () => { fireEvent.changeText(u.getByPlaceholderText(SK.araYer), "Fantom"); });
    expect(u.getByTestId("hasta-sayac").props.children).toBe("1 / 2 örnek gösteriliyor");
  });

  it("kimliksiz → hasta sayacı yok", async () => {
    mockOpEposta = "";
    const u = await hastalar([HASTA("p1", "Boncuk")]);
    expect(u.queryByTestId("hasta-sayac")).toBeNull();
  });

  it("EN: '1 patient' / '2 patients'", async () => {
    await enYap();
    const u = await hastalar([HASTA("p1", "Boncuk")]);
    expect(u.getByTestId("hasta-sayac").props.children).toBe("1 patient");
  });
});
