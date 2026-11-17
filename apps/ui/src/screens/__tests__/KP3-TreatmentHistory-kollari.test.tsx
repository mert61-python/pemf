/**
 * KP-3 C · src/screens/TreatmentHistoryScreen.tsx kapsanmayan kolları — her test bir DAVRANIŞ iddiası (crashGuards düzeneği):
 *  - Sayfalama: tam sayfa (50) gelince "Daha fazla" görünür; basınca SON kaydın kimliğiyle (cursor) sonraki sayfa istenir ve listeye
 *    EKLENİR; eksik sayfa / boş yanıt gelince düğme kalkar.
 *  - Notlar: kalem → düzenleme; "Kaydet" notu seans kimliğiyle gönderir, başarıda bildirim + liste yenilenir, başarısızlıkta hata; iptal
 *    ESKİ notu geri koyar.
 *  - Dışa aktarma: yüklenmemiş kayıt varken (hasMore) PDF / görünen CSV ONAY ister — reddedilirse indirme YOK; 200'den fazla kayıtta PDF
 *    sınır uyarısı + ilk 200 gider. Tekil PDF o seansın kimliğiyle iner.
 *  - Bilinmeyen seans durumu okunaklı (ilk harf büyük) gösterilir. Kart → bobin detayı açılır / kapanır.
 *  - Toplu silme: onay reddi → istek yok; sunucu reddi → ileti; "Benim" kapsamına dönüş.
 * SAHTE: apiClient (ağ sınırı) · dosya indirme servisi · bildirim · detay modalı (aldığı props kaydedilir).
 */
const mockAlert = jest.fn();
const mockConfirm = jest.fn(async (..._a: unknown[]) => true);
const mockApiGet = jest.fn();
const mockApiPost = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  platformAlert: (...a: unknown[]) => mockAlert(...a),
  platformConfirm: (...a: unknown[]) => mockConfirm(...a),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://192.168.1.5:8000/api" } }));
const mockIndir = jest.fn();
jest.mock("@/services/dosyaIndir", () => ({
  downloadFileWithAuth: (...a: unknown[]) => mockIndir(...a),
  backendBuMakinede: () => false,
}));
const mockToast = jest.fn();
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
let mockDetay: { visible: boolean; sessionId: unknown; onClose: () => void } | null = null;
jest.mock("@/components/domain/SessionDetailModal", () => ({
  SessionDetailModal: (p: { visible: boolean; sessionId: unknown; onClose: () => void }) => { mockDetay = p; return null; },
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ userMode: "veterinarian", isExpert: true, isResearcher: false }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "v@x.com" } }) }));

import React from "react";
import { act, fireEvent, render } from "@testing-library/react-native";
import { Edit3 } from "lucide-react-native";
import i18n from "i18next";
import { TreatmentHistoryScreen } from "@/screens/TreatmentHistoryScreen";
import { StatusPill } from "@/components/ui/StatusPill";
import { profilSozlugu } from "@/utils/profilSozlugu";

const T = (k: string, o?: object): string => (i18n.t as unknown as (k: string, o?: object) => string)(k, o);
const seans = (id: number, ek: Record<string, unknown> = {}) => ({
  id, patient_name: `Hasta-${id}`, session_status: "completed", operator_email: "v@x.com", patient_notes: "",
  session_date: "2026-11-01", treatment_mode: "Manuel", duration_minutes: 20, frequency_hz: 50, ...ek,
});
const sayfa = (bas: number, adet: number) => Array.from({ length: adet }, (_, i) => seans(bas + i));

type U = ReturnType<typeof render>;
async function ekran(ilk: unknown[]) {
  mockApiGet.mockImplementationOnce(async () => ilk);
  const u = render(<TreatmentHistoryScreen />);
  await act(async () => {});
  return u;
}
async function bas(u: U, etiket: string) { await act(async () => { fireEvent.press(u.getByLabelText(etiket)); }); }
async function metin(u: U, m: string) { await act(async () => { fireEvent.press(u.getByText(m)); }); }

beforeEach(() => {
  mockAlert.mockReset();
  mockConfirm.mockReset();
  mockConfirm.mockImplementation(async () => true);
  mockApiGet.mockReset();
  mockApiGet.mockResolvedValue([]);
  mockApiPost.mockReset();
  mockApiPost.mockResolvedValue({ status: "success" });
  mockIndir.mockReset();
  mockToast.mockReset();
  mockDetay = null;
});

describe("sayfalama", () => {
  it("tam sayfa → 'Daha fazla'; SON kaydın kimliğiyle sonraki sayfa EKLENİR; eksik sayfa gelince düğme kalkar", async () => {
    const u = await ekran(sayfa(1, 50));
    mockApiGet.mockImplementationOnce(async () => sayfa(51, 10));
    await bas(u, T("seans.gecmis.dahaFazlaEtiket"));
    expect(mockApiGet).toHaveBeenLastCalledWith("/history/?limit=50&cursor=50", null);
    expect(u.getByText("Hasta-60")).toBeTruthy();
    expect(u.getByText("Hasta-1")).toBeTruthy(); // önceki sayfa KORUNUR (eklenir, değiştirilmez)
    expect(u.queryByLabelText(T("seans.gecmis.dahaFazlaEtiket"))).toBeNull();
  });

  it("sonraki sayfa boş gelirse düğme kalkar, liste değişmez", async () => {
    const u = await ekran(sayfa(1, 50));
    mockApiGet.mockImplementationOnce(async () => []);
    await bas(u, T("seans.gecmis.dahaFazlaEtiket"));
    expect(u.queryByLabelText(T("seans.gecmis.dahaFazlaEtiket"))).toBeNull();
    expect(u.getByText("Hasta-50")).toBeTruthy();
  });
});

describe("notlar", () => {
  it("kalem → düzenle; Kaydet notu seans kimliğiyle gönderir (başarı: bildirim + yenile; hata: ileti); iptal eski notu geri koyar", async () => {
    mockApiGet.mockResolvedValue([seans(7, { patient_notes: "eski not" })]); // yenileme de aynı listeyi döner
    const u = await ekran([seans(7, { patient_notes: "eski not" })]);
    await act(async () => { fireEvent.press(u.UNSAFE_getAllByType(Edit3)[0]); });
    await act(async () => { fireEvent.changeText(u.getByPlaceholderText(T("seans.gecmis.notPlaceholder")), "yeni not"); });
    const okuma = mockApiGet.mock.calls.length;
    await metin(u, T("ayarlar.kaydet"));
    expect(mockApiPost).toHaveBeenCalledWith("/history/update_notes", { session_id: 7, notes: "yeni not" }, { status: "error" });
    expect(mockToast).toHaveBeenLastCalledWith(T("seans.gecmis.notlarKaydedildi"), "success");
    expect(mockApiGet.mock.calls.length).toBeGreaterThan(okuma);

    await act(async () => { fireEvent.press(u.UNSAFE_getAllByType(Edit3)[0]); });
    mockApiPost.mockResolvedValueOnce({ status: "error" });
    await metin(u, T("ayarlar.kaydet"));
    expect(mockToast).toHaveBeenLastCalledWith(T("seans.gecmis.notlarKaydedilemedi"), "error");
    await act(async () => { fireEvent.changeText(u.getByPlaceholderText(T("seans.gecmis.notPlaceholder")), "vazgeçilecek"); });
    await metin(u, T("ayarlar.iptal"));
    expect(u.queryByPlaceholderText(T("seans.gecmis.notPlaceholder"))).toBeNull();
    await act(async () => { fireEvent.press(u.UNSAFE_getAllByType(Edit3)[0]); });
    expect(u.getByPlaceholderText(T("seans.gecmis.notPlaceholder")).props.value).toBe("eski not");
  });
});

describe("dışa aktarma", () => {
  it("yüklenmemiş kayıt varken PDF ve görünen CSV ONAY ister; reddedilirse indirme YOK", async () => {
    const u = await ekran(sayfa(1, 50));
    mockConfirm.mockImplementation(async () => false);
    await metin(u, T("seans.gecmis.pdfGorunen"));
    await metin(u, T("seans.gecmis.csvGorunen"));
    expect(mockConfirm.mock.calls.map((c) => c[0])).toEqual([T("seans.gecmis.yalnizYuklenen"), T("seans.gecmis.yalnizYuklenen")]);
    expect(mockIndir).not.toHaveBeenCalled();
    mockConfirm.mockImplementation(async () => true);
    await metin(u, T("seans.gecmis.csvGorunen"));
    expect(String(mockIndir.mock.calls[0][0])).toMatch(/export_csv\?session_ids=1,2,/);
  });

  it("200'den fazla kayıtta PDF sınır uyarısı + yalnız ilk 200 gider; tekil PDF seans kimliğiyle", async () => {
    const u = await ekran(sayfa(1, 50));
    for (let i = 0; i < 4; i++) {
      mockApiGet.mockImplementationOnce(async () => sayfa(51 + i * 50, 50));
      await bas(u, T("seans.gecmis.dahaFazlaEtiket"));
    }
    await metin(u, T("seans.gecmis.pdfGorunen"));
    expect(mockAlert).toHaveBeenCalledWith(T("seans.gecmis.cokKayit"), T("seans.gecmis.pdfSinir", { adet: 250, enCok: 200 }));
    const url = String(mockIndir.mock.calls[0][0]);
    expect(url.split("session_ids=")[1].split(",")).toHaveLength(200);
    mockIndir.mockReset();
    await act(async () => { fireEvent.press(u.getAllByLabelText(T("seans.gecmis.pdfEtiketi"))[0]); });
    expect(String(mockIndir.mock.calls[0][0])).toBe("http://192.168.1.5:8000/api/history/export_pdf?session_ids=1");
    expect(String(mockIndir.mock.calls[0][1])).toContain("Hasta-1");
  }, 30000);
});

describe("kart + toplu silme", () => {
  it("bilinmeyen durum okunaklı; kart bobin detayını açar / kapanır", async () => {
    const u = await ekran([seans(3, { session_status: "beklemede_x" }), seans(4, { session_status: "running" })]);
    expect(u.getByText("Beklemede_x")).toBeTruthy();
    await act(async () => { fireEvent.press(u.getAllByLabelText(T("seans.gecmis.detayiAc"))[0]); });
    expect(mockDetay).toMatchObject({ visible: true, sessionId: 3 });
    await act(async () => { mockDetay!.onClose(); });
    expect(mockDetay).toMatchObject({ visible: false, sessionId: null });
  });

  it("toplu silmede onay reddi → istek yok; sunucu reddi → ileti; 'Benim' kapsamına dönüş", async () => {
    const u = await ekran([seans(1), seans(2, { operator_email: "baska@x.com" })]);
    await bas(u, T("seans.gecmis.tumKapsamEtiketi", { tumKapsamKucuk: profilSozlugu({ researcher: false }).tumKapsamKucuk }));
    expect(u.getByText("Hasta-2")).toBeTruthy();
    await bas(u, T("seans.gecmis.secimKipiEtiketi"));
    await act(async () => { fireEvent.press(u.getByTestId("gecmis-secim-1")); });
    mockConfirm.mockImplementationOnce(async () => false);
    await act(async () => { fireEvent.press(u.getByTestId("gecmis-secim-cubugu-sil")); });
    expect(mockApiPost).not.toHaveBeenCalled();
    mockApiPost.mockResolvedValueOnce({ status: "error" });
    await act(async () => { fireEvent.press(u.getByTestId("gecmis-secim-cubugu-sil")); });
    expect(mockApiPost.mock.calls[0][0]).toBe("/history/delete_bulk");
    expect((mockApiPost.mock.calls[0][1] as { session_ids: number[] }).session_ids).toEqual([1]);
    expect(mockToast).toHaveBeenLastCalledWith(T("hasta.sil.topluBasarisizKisa"), "error");
    await bas(u, T("seans.gecmis.benimEtiket"));
    expect(u.queryByText("Hasta-2")).toBeNull();
  });
});

// KP-7 B (deyim ölçüsü): durum hapı — tamamlandı → yeşil (online), sürüyor → sarı (warning), YARIDA KALDI / hata / kurtarıldı → gri
// (offline) — yarıda kalan seans "tamamlandı" gibi yeşil GÖRÜNMEZ.
describe("KP-7 B · durum hapı", () => {
  it("tamamlandı yeşil, sürüyor sarı; yarıda kaldı / hata / kurtarıldı gri", async () => {
    const u = await ekran([
      seans(11, { session_status: "completed" }),
      seans(12, { session_status: "running" }),
      seans(13, { session_status: "interrupted" }),
      seans(14, { session_status: "error" }),
      seans(15, { session_status: "aborted_recovered" }),
    ]);
    const durumlar = u.UNSAFE_getAllByType(StatusPill).map((p) => p.props.state);
    expect(durumlar).toEqual(["online", "warning", "offline", "offline", "offline"]);
  });
});
