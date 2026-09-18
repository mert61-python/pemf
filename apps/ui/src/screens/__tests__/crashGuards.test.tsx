// Author: mertaygn, cglrgrkn
/**
 * CRASH-GUARD zinciri — bu denetimde bulunan üç ekran çökmesinin KÖKÜ tek satırdı:
 * `parseJsonSafe` boş 2xx gövdesinde ÇAĞIRANIN fallback'i yerine sabit `{}` dönüyordu.
 * Sonuç: `apiGet<T[]|null>(..., null)` → `null` değil `{}` alıyor, `data !== null` kapısını
 * geçiyor ve `.filter`/`.map` TypeError atıyordu.
 *
 * En ağır sonuç Ana Ekran'daydı: `snapshot.activeTreatment.isActive` patlayınca ErrorBoundary
 * devreye giriyor ve ACİL DURDUR butonu O EKRANDA olduğu için donanım çalışırken durdurma
 * kontrolü ekrandan KAYBOLUYORDU. Bu testler o zincirin her halkasını kilitler.
 */
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(),
  apiPost: jest.fn(async () => null),
  platformAlert: jest.fn(),
  platformConfirm: jest.fn(async () => true),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({
  serviceConfig: { apiBaseUrl: "http://192.168.1.5:8000/api" },
}));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock("@/hooks/useSessionControl", () => ({
  useSessionControl: () => ({
    isActive: false, treatment: null, elapsedSec: 0, remainingSec: 0,
    loading: false, stopping: false, error: null, lastError: () => null,
    startSession: jest.fn(), stopSession: jest.fn(), emergencyStop: jest.fn(),
  }),
}));

let mockSnap: any;
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({
    snapshot: mockSnap, wsConnected: true, connectionQuality: "live",
    haveRealData: true, telemetryStale: false, sensorHistory: {},
    unreadCount: 0, markAllRead: jest.fn(), clearNotifications: jest.fn(),
    refresh: jest.fn(), reconnect: jest.fn(), aiVisionFresh: false,
  }),
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian" }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));

import React from "react";
import { render, waitFor } from "@testing-library/react-native";
import { apiGet } from "@/services/apiClient";
import { DashboardScreen } from "@/screens/DashboardScreen";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { KpiDashboardScreen } from "@/screens/KpiDashboardScreen";

const mockApiGet = apiGet as jest.Mock;

const FULL_SNAPSHOT = {
  gateway: "online", mqtt: "online", stm: "online",
  patient: { name: "", species: "", breed: "", owner: "" },
  activeTreatment: { isActive: false, mode: "Sistem Hazır", frequencyHz: 0, intensityMt: 0, remainingMin: 0, elapsedSec: 0, durationSec: 0 },
  notifications: [], coils: [], system: {}, sessions: [],
};

beforeEach(() => {
  mockApiGet.mockReset();
  mockApiGet.mockResolvedValue(null);
  mockSnap = { ...FULL_SNAPSHOT };
});

// ── Ana Ekran: en kritik halka (E-stop bu ekranda) ───────────────────────────
it("KRİTİK: snapshot `activeTreatment` İÇERMESE BİLE Ana Ekran çökmez (E-stop erişimi korunur)", () => {
  mockSnap = { coils: [], notifications: [] }; // backend alanı atladı / boş gövde geldi
  expect(() => render(<DashboardScreen />)).not.toThrow();
});

it("Ana Ekran: snapshot TAMAMEN boş `{}` olsa da çökmez (parseJsonSafe zinciri)", () => {
  mockSnap = {};
  expect(() => render(<DashboardScreen />)).not.toThrow();
});

it("Ana Ekran: donanım seans DIŞINDA çalışıyorsa uyarır (isActive false ama bobin running)", () => {
  mockSnap = { ...FULL_SNAPSHOT, coils: [{ id: 1, running: true, connected: true }] };
  const { getByText } = render(<DashboardScreen />);
  expect(getByText(/DONANIM ÇALIŞIYOR/)).toBeTruthy();
});

it("KRİTİK: bobin verisi NORMALİZE EDİLMEMİŞ gelse de (undefined/string alanlar) Ana Ekran çökmez", () => {
  // Bu testi yazarken bulundu: CoilCard `coil.magneticMt.toFixed(2)` çağırıyordu ve alanların
  // sayı olmasına LiveDataContext'in normalize etmesine GÜVENİYORDU. Normalize etmeyen tek bir
  // çağrı yeri Ana Ekran'ı (dolayısıyla ACİL DURDUR'u) çökertirdi. Kart artık kendi girdisini doğrular.
  mockSnap = {
    ...FULL_SNAPSHOT,
    coils: [
      { id: 1, running: true, connected: true },                              // alanlar YOK
      { id: 2, running: false, connected: true, magneticMt: "44.5", objectTemp: null }, // yanlış tip
    ],
  };
  const { getAllByText } = render(<DashboardScreen />);
  expect(getAllByText(/—|44\.50/).length).toBeGreaterThan(0);
});

// ── Tedavi Geçmişi ───────────────────────────────────────────────────────────
it("KRİTİK: /history dizi DEĞİL nesne dönerse Geçmiş ekranı çökmez (beyaz ekran yok)", async () => {
  mockApiGet.mockResolvedValue({} as any); // boş 2xx gövdesinin eski davranışı
  const { getByText } = render(<TreatmentHistoryScreen />);
  await waitFor(() => expect(getByText(/Geçmiş kayıtlar yüklenemedi|kayıt bulunamadı|yüklenemedi/i)).toBeTruthy());
});

it("Geçmiş: /history null dönerse hata durumu gösterir, çökmez", async () => {
  mockApiGet.mockResolvedValue(null);
  expect(() => render(<TreatmentHistoryScreen />)).not.toThrow();
  await waitFor(() => expect(mockApiGet).toHaveBeenCalled());
});

// ── KPI / Raporlar ───────────────────────────────────────────────────────────
it("KRİTİK: KPI yanıtı `last7Days`/`modeDistribution` İÇERMESE BİLE Raporlar çökmez", async () => {
  // Eski kod `setKpi(data)` ile state'i TÜMÜYLE değiştiriyordu → alanlar undefined kalıp .map patlıyordu.
  mockApiGet.mockResolvedValue({ totalSessions: 12 } as any);
  const { queryByText } = render(<KpiDashboardScreen />);
  await waitFor(() => expect(mockApiGet).toHaveBeenCalled());
  expect(queryByText(/12/)).toBeTruthy();
});

it("KPI: bozuk tipli alanlar (dizi yerine string) güvenli varsayılana düşer", async () => {
  mockApiGet.mockResolvedValue({ totalSessions: 3, last7Days: "bozuk", modeDistribution: 7 } as any);
  expect(() => render(<KpiDashboardScreen />)).not.toThrow();
  await waitFor(() => expect(mockApiGet).toHaveBeenCalled());
});
