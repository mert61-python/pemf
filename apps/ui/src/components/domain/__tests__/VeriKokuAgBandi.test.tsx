// Author: mertaygn, cglrgrkn
/**
 * Y118 — veri klasörü AĞ PAYLAŞIMINDAYSA arayüz uyarısı (sağlık ucu `veriKokuAgda`).
 *
 * Kilitlenen davranışlar:
 *   - `veriKokuAgda: true` → bant GÖRÜNÜR, sahibin metnini söyler ("SQLite bu kipte güvenilir değil — yerel diske taşıyın"),
 *     sağlığı `/health` (taban `/api`) ucundan sessiz okur, kapatma düğmesi YOK;
 *   - `false` / `null` (tünel istemcisi) / alan yok (eski backend) / sağlık okunamadı → bant YOK (sahte uyarı yok);
 *   - ⚠️ HASTA GÜVENLİĞİ: donanım çalışırken (seans ya da çalışan bobin) GÖSTERİLMEZ.
 */
jest.mock("@/services/apiClient", () => ({ apiGet: jest.fn() }));

const mockSnapshot: { activeTreatment?: { isActive: boolean }; coils?: { running: boolean }[] } = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnapshot }),
}));

import { act, render, waitFor } from "@testing-library/react-native";
import { apiGet } from "@/services/apiClient";
import { VeriKokuAgBandi, veriKokuAgBandiMetni } from "@/components/domain/VeriKokuAgBandi";

const mockGet = apiGet as jest.Mock;

beforeEach(() => {
  mockGet.mockReset();
  delete mockSnapshot.activeTreatment;
  delete mockSnapshot.coils;
});

it("KRİTİK: veriKokuAgda=true iken bant GÖRÜNÜR, sahibin metnini söyler, kapatılamaz", async () => {
  mockGet.mockResolvedValue({ veriKokuAgda: true });
  const { getByText, queryByLabelText } = render(<VeriKokuAgBandi />);
  await waitFor(() => expect(getByText(/Veri klasörü ağ paylaşımında/)).toBeTruthy());
  expect(getByText(/SQLite bu kipte güvenilir değil — yerel diske taşıyın/)).toBeTruthy();
  expect(queryByLabelText(/kapat/i)).toBeNull();
  expect(mockGet).toHaveBeenCalledWith("/health", null, { silent: true });
});

it.each([
  ["yerel disk (false)", { veriKokuAgda: false }],
  ["tünel istemcisi / bilinemedi (null)", { veriKokuAgda: null }],
  ["alan yok (eski backend)", { status: "online" }],
  ["sağlık okunamadı", null],
])("KARŞIT: %s → bant YOK", async (_ad, yanit) => {
  mockGet.mockResolvedValue(yanit);
  const { queryByText } = render(<VeriKokuAgBandi />);
  await act(async () => {});
  expect(queryByText(/ağ paylaşımında/)).toBeNull();
});

it.each([
  ["seans sürerken", () => { mockSnapshot.activeTreatment = { isActive: true }; }],
  ["seans kaydı yokken bobin çalışırken", () => { mockSnapshot.coils = [{ running: true }]; }],
])("KRİTİK — HASTA GÜVENLİĞİ: %s gösterilmez", async (_ad, kur) => {
  kur();
  mockGet.mockResolvedValue({ veriKokuAgda: true });
  const { queryByText } = render(<VeriKokuAgBandi />);
  await act(async () => {});
  expect(queryByText(/ağ paylaşımında/)).toBeNull();
});

it("metin fonksiyonu yalnız AÇIK true'da metin verir", () => {
  expect(veriKokuAgBandiMetni({ veriKokuAgda: true })?.baslik).toMatch(/ağ paylaşımında/);
  expect(veriKokuAgBandiMetni({ veriKokuAgda: false })).toBeNull();
  expect(veriKokuAgBandiMetni(null)).toBeNull();
});
