// Author: mertaygn, cglrgrkn
/**
 * D1.37 — "sağlık ucu VE ARAYÜZ 'göç bekliyor' desin" (1-B bağımsız inceleme i2: arayüzde `dbReady`/`dbSebep`
 * okuyan 0 satır vardı; operatör durumu ancak seans başlatınca, hasta masadayken öğreniyordu).
 *
 * Kilitlenen davranışlar:
 *   - `dbReady: false` → bant GÖRÜNÜR ve backend'in `dbSebep` metnini AYNEN gösterir (göç bekliyor);
 *   - `dbReady: true` / alan yok (eski backend) / sağlık okunamadı → bant YOK (sahte uyarı yok);
 *   - durum düzelince (yoklama `true` döner) bant KALKAR;
 *   - bant ACİL DURDUR'un çalıştığını söyler (Ö.4-Y8) ve sağlığı `/health` (taban `/api`) ucundan okur.
 */
jest.mock("@/services/apiClient", () => ({ apiGet: jest.fn() }));

import { act, render, waitFor } from "@testing-library/react-native";
import { apiGet } from "@/services/apiClient";
import { KAYIT_DB_YOKLAMA_MS, KayitDbBandi, kayitDbBandiMetni } from "@/components/domain/KayitDbBandi";

const mockGet = apiGet as jest.Mock;
const GOC =
  "Hasta veritabanı göç bekliyor: at-rest şifreleme göçü tamamlanmadı (dosya kilitli olabilir); dosya " +
  "korunuyor, karantinaya alınmadı. Cihazı yeniden başlatın — göç yeniden denenecek.";

beforeEach(() => {
  mockGet.mockReset();
});

afterEach(() => {
  jest.useRealTimers();
});

it("KRİTİK: dbReady=false iken bant GÖRÜNÜR ve backend'in 'göç bekliyor' metnini AYNEN gösterir", async () => {
  mockGet.mockResolvedValue({ dbReady: false, dbSebep: GOC });
  const { getByText } = render(<KayitDbBandi />);
  await waitFor(() => expect(getByText(/yeni seans BAŞLATILAMAZ/)).toBeTruthy());
  expect(getByText(/göç bekliyor: at-rest şifreleme göçü tamamlanmadı/)).toBeTruthy();
  expect(getByText(/ACİL DURDUR ve bobin durdurma çalışır/)).toBeTruthy();
  expect(mockGet).toHaveBeenCalledWith("/health", null, { silent: true });
});

it.each([
  ["dbReady true", { dbReady: true, dbSebep: null }],
  ["alan yok (eski backend)", { status: "ok" }],
  ["sağlık okunamadı", null],
])("KARŞIT: %s → bant YOK", async (_ad, yanit) => {
  mockGet.mockResolvedValue(yanit);
  const { queryByText } = render(<KayitDbBandi />);
  await act(async () => {});
  expect(queryByText(/kayıt veritabanı hazır değil/)).toBeNull();
});

it("KRİTİK: durum düzelince (sonraki yoklama dbReady=true) bant KALKAR", async () => {
  jest.useFakeTimers();
  mockGet.mockResolvedValueOnce({ dbReady: false, dbSebep: GOC }).mockResolvedValue({ dbReady: true });
  const { queryByText } = render(<KayitDbBandi />);
  await act(async () => {});
  expect(queryByText(/yeni seans BAŞLATILAMAZ/)).toBeTruthy();
  await act(async () => {
    jest.advanceTimersByTime(KAYIT_DB_YOKLAMA_MS);
  });
  await act(async () => {});
  expect(queryByText(/yeni seans BAŞLATILAMAZ/)).toBeNull();
});

it("dbSebep boşsa genel metin; sebep yine de 'seans başlatılamaz' der", () => {
  const m = kayitDbBandiMetni({ dbReady: false, dbSebep: "  " });
  expect(m?.aciklama).toMatch(/yeni seans başlatılamaz/i);
  expect(kayitDbBandiMetni({ dbReady: undefined })).toBeNull();
});
