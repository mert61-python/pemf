// Author: mertaygn, cglrgrkn
/**
 * KURTARMA KODU BANDI (2026-08-09 denetimi, ENGEL).
 *
 * Hasta kayıtları bu MAKİNEYE bağlı bir anahtarla şifreli. Kurtarma kodu makine dışına
 * kopyalanmazsa disk arızasında off-site yedekler bile SONSUZA DEK açılamaz. Kod üretiliyor
 * ve dosyaya yazılıyordu ama operatöre YALNIZCA log'dan söyleniyordu — yani hiç söylenmiyordu.
 *
 * Kilitlenen davranışlar:
 *   - backend `warn:true` derse bant GÖRÜNÜR ve kapatma düğmesi YOKTUR (onaya kadar kalıcı),
 *   - onaydan sonra SUSAR,
 *   - ⚠️ SEANS SÜRERKEN gösterilmez (hasta üzerindeyken ekranı bölme),
 *   - kod ASLA istemcide gösterilmez (yalnız dosya YOLU).
 */
jest.mock("@/services/apiClient", () => ({ apiGet: jest.fn(), apiPost: jest.fn() }));

const mockSnapshot: { activeTreatment?: { isActive: boolean } } = {};
jest.mock("@/context/LiveDataContext", () => ({
  useLiveData: () => ({ snapshot: mockSnapshot }),
}));

import { render, waitFor, act, fireEvent } from "@testing-library/react-native";
import { apiGet, apiPost } from "@/services/apiClient";
import { RecoveryCodeBanner } from "@/components/domain/RecoveryCodeBanner";

const mockGet = apiGet as jest.Mock;
const mockPost = apiPost as jest.Mock;

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  delete mockSnapshot.activeTreatment;
});

it("KRİTİK: backend uyarı isterse bant GÖRÜNÜR", async () => {
  mockGet.mockResolvedValue({ warn: true, codeFilePath: "C:\\ProgramData\\PEMF\\KURTARMA-KODU.txt" });
  const { getByText, queryByText } = render(<RecoveryCodeBanner />);
  await waitFor(() => expect(getByText(/Kurtarma kodunuzu makine dışına/)).toBeTruthy());
  expect(queryByText(/KURTARMA-KODU\.txt/)).toBeTruthy();   // operatör dosyayı bulabilmeli
});

it("uyarı gerekmiyorsa HİÇ çizilmez", async () => {
  mockGet.mockResolvedValue({ warn: false });
  const { queryByText } = render(<RecoveryCodeBanner />);
  await act(async () => {});
  expect(queryByText(/Kurtarma kodunuzu/)).toBeNull();
});

it("KRİTİK — HASTA GÜVENLİĞİ: SEANS SÜRERKEN gösterilmez", async () => {
  mockSnapshot.activeTreatment = { isActive: true };
  mockGet.mockResolvedValue({ warn: true });
  const { queryByText } = render(<RecoveryCodeBanner />);
  await act(async () => {});
  expect(queryByText(/Kurtarma kodunuzu/)).toBeNull();
});

it("KRİTİK: KAPATMA düğmesi YOK — ertelemenin bedeli tüm klinik geçmişi", async () => {
  mockGet.mockResolvedValue({ warn: true });
  const { getByText, queryByLabelText } = render(<RecoveryCodeBanner />);
  await waitFor(() => expect(getByText(/Kurtarma kodunuzu/)).toBeTruthy());
  expect(queryByLabelText(/kapat/i)).toBeNull();
});

it("onaylanınca bant SUSAR ve backend'e yazılır", async () => {
  mockGet.mockResolvedValue({ warn: true });
  mockPost.mockResolvedValue({ status: "success" });
  const { getByLabelText, queryByText } = render(<RecoveryCodeBanner />);
  await waitFor(() => expect(getByLabelText(/Kurtarma kodunu makine dışına/)).toBeTruthy());

  await act(async () => { fireEvent.press(getByLabelText(/Kurtarma kodunu makine dışına/)); });

  expect(mockPost).toHaveBeenCalledWith("/system/recovery-ack", {}, null, { silent: true });
  await waitFor(() => expect(queryByText(/Kurtarma kodunuzu/)).toBeNull());
});

it("onay backend'de başarısızsa bant KALIR (yanlış güvence verme)", async () => {
  mockGet.mockResolvedValue({ warn: true });
  mockPost.mockResolvedValue(null);                       // cihaza ulaşılamadı
  const { getByLabelText, getByText } = render(<RecoveryCodeBanner />);
  await waitFor(() => expect(getByLabelText(/Kurtarma kodunu makine dışına/)).toBeTruthy());
  await act(async () => { fireEvent.press(getByLabelText(/Kurtarma kodunu makine dışına/)); });
  expect(getByText(/Kurtarma kodunuzu/)).toBeTruthy();
});

it("cihaza ulaşılamıyorsa SESSİZCE gizlenir (internetsiz klinik akışı bölünmesin)", async () => {
  mockGet.mockResolvedValue(null);
  const { queryByText } = render(<RecoveryCodeBanner />);
  await act(async () => {});
  expect(queryByText(/Kurtarma kodunuzu/)).toBeNull();
  expect(mockGet).toHaveBeenCalledWith("/system/recovery-status", null, { silent: true });
});
