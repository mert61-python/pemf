// Author: mertaygn, cglrgrkn
/**
 * I18N-P1 · Seans geçmişi (TreatmentHistoryScreen), seans detayı (SessionDetailModal) ve dışa aktarım iletileri (dosyaIndir) iki dilde.
 * TR görünüm göç öncesiyle BAYT BAYT aynı; EN doğru ve sade. ⚠️ Beklenen metinler BURADA sabittir (üründen okunmaz).
 * VERİ: sunucuya giden istek yolları / dosya adları / ham durum değerleri EN iken de aynıdır.
 */
jest.mock("react-native", () => {
  const RN = jest.requireActual("react-native");
  RN.Platform.OS = "web";
  return RN;
});

let mockSeanslar: unknown = [];
let mockDetay: unknown = null;
const mockApiPost = jest.fn(async (..._a: unknown[]): Promise<unknown> => ({ status: "success" }));
const mockToast = jest.fn();
const mockIndir = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: jest.fn(async (yol: string) => (/\/details$/.test(yol) ? mockDetay : mockSeanslar)),
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  platformConfirm: jest.fn(async () => false),
  platformAlert: jest.fn(),
  authHeaders: jest.fn(() => ({})),
}));
jest.mock("@/services/config", () => ({ serviceConfig: { apiBaseUrl: "http://127.0.0.1:8000/api" } }));
jest.mock("@/components/ui/ToastProvider", () => ({ useToast: () => ({ showToast: mockToast }) }));
jest.mock("@/context/AppNavContext", () => ({ useAppNav: () => ({ selectedPatient: null }) }));
jest.mock("@/context/AuthContext", () => ({ useAuth: () => ({ session: { email: "a@x.com" } }) }));
jest.mock("@/context/OperatorContext", () => ({
  useOperatorOptional: () => ({ operatorEmail: "a@x.com", operators: [], kimlikDbOkunamiyor: false }),
}));
jest.mock("@/context/UserModeContext", () => ({ useUserMode: () => ({ isExpert: false, isResearcher: false }) }));
jest.mock("@/services/dosyaIndir", () => ({ downloadFileWithAuth: (...a: unknown[]) => mockIndir(...a) }));
jest.mock("@/services/backendKonumu", () => ({ backendBuMakinede: () => false }));
jest.mock("expo-file-system/legacy", () => ({ cacheDirectory: "file:///", downloadAsync: jest.fn(), deleteAsync: jest.fn() }));
jest.mock("expo-sharing", () => ({ isAvailableAsync: jest.fn(async () => false), shareAsync: jest.fn() }));

import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import i18n from "i18next";
import React from "react";

import { SessionDetailModal } from "@/components/domain/SessionDetailModal";
import { TreatmentHistoryScreen, zatenSilinmisSeans } from "@/screens/TreatmentHistoryScreen";
import { platformConfirm } from "@/services/apiClient";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };

const KAYIT = (id: number, ek: Record<string, unknown> = {}) => ({
  id,
  patient_name: `Hasta${id}`,
  session_date: "2026-10-01",
  start_time: "10:00",
  session_status: "completed",
  operator_email: "a@x.com",
  treatment_mode: "Manuel",
  target_condition: "Eklem",
  duration_minutes: 20,
  frequency_hz: 10,
  intensity_mt: null,
  patient_notes: "",
  ...ek,
});

beforeEach(() => {
  mockSeanslar = [KAYIT(1, { patient_name: "Tekir" }), KAYIT(2, { session_status: "emergency_stopped" }), KAYIT(3, { patient_name: "", session_status: "hardware_rejected" })];
  mockDetay = null;
  mockApiPost.mockClear();
  mockToast.mockClear();
  mockIndir.mockClear();
  (platformConfirm as jest.Mock).mockClear();
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
async function ekran() {
  const u = render(<TreatmentHistoryScreen />);
  await waitFor(() => expect(u.getAllByText(/Tekir/).length).toBeGreaterThan(0));
  return u;
}

describe("TreatmentHistoryScreen", () => {
  it("TR: liste, durum rozetleri, kart etiketleri, düğmeler göç öncesiyle aynı", async () => {
    const u = await ekran();
    const m = metin(u);
    for (const s of [
      "Tamamlandı",
      "Acil Durduruldu",
      "Donanım Reddetti",
      "Bilinmeyen Hasta",
      "Bobin detayını gör ›",
      "Mod",
      "Hedef",
      "Süre",
      "20 dk",
      "Frekans",
      "10 Hz",
      "Notlar:",
      "Not eklenmemiş.",
      "Benim Seanslarım",
      "Görünenleri Excel/CSV İndir",
      "Görünenleri PDF İndir",
      "Seç",
    ]) {
      expect(m).toContain(s);
    }
    expect(u.getByPlaceholderText("Hasta, Not veya Tarih ara...")).toBeTruthy();
    expect(u.getByLabelText("Benim seanslarım")).toBeTruthy();
    expect(u.getByLabelText("Tüm klinik seansları")).toBeTruthy();
    expect(u.getByLabelText("Tekir kaydını sil")).toBeTruthy();
    expect(u.getByLabelText("Bilinmeyen Hasta kaydını sil")).toBeTruthy();
    expect(u.getAllByLabelText("Seans detayını aç").length).toBe(3);
    expect(u.getAllByLabelText("Seans raporunu PDF olarak al").length).toBe(3);
    expect(u.getByLabelText("Toplu seçim kipini aç veya kapat")).toBeTruthy();
    expect(zatenSilinmisSeans()).toBe("Bu seans zaten silinmiş — liste yenilendi.");
  });

  it("EN: liste, durum rozetleri, kart etiketleri, düğmeler; Türkçe harf KALMADI", async () => {
    await enYap();
    const u = await ekran();
    const m = metin(u);
    for (const s of [
      "Completed",
      "Emergency Stopped",
      "Hardware Rejected",
      "Unknown Patient",
      "View coil details ›",
      "Mode",
      "Target",
      "Duration",
      "20 min",
      "Frequency",
      "10 Hz",
      "Notes:",
      "No note added.",
      "My Sessions",
      "Download Visible as Excel/CSV",
      "Download Visible as PDF",
      "Select",
    ]) {
      expect(m).toContain(s);
    }
    expect(m).not.toMatch(/[çğıöşüÇĞİÖŞÜ]/); // arayüz metni iki dilli: EN ekranda Türkçe harf KALMADI (veri alanları ASCII)
    expect(u.getByPlaceholderText("Search patient, note or date...")).toBeTruthy();
    expect(u.getByLabelText("My sessions")).toBeTruthy();
    expect(u.getByLabelText("All clinic sessions")).toBeTruthy();
    expect(u.getByLabelText("Delete the record of Tekir")).toBeTruthy();
    expect(u.getByLabelText("Delete the record of Unknown Patient")).toBeTruthy();
    expect(u.getAllByLabelText("Open session details").length).toBe(3);
    expect(u.getAllByLabelText("Get the session report as a PDF").length).toBe(3);
    expect(u.getByLabelText("Toggle multi-select mode")).toBeTruthy();
    expect(zatenSilinmisSeans()).toBe("This session has already been deleted — the list was refreshed.");
  });

  it("VERİ: dışa aktarım dosya adları / URL EN iken de TR ile aynı", async () => {
    const calis = async () => {
      mockIndir.mockClear();
      const u = await ekran();
      await act(async () => {
        fireEvent.press(u.getByText(/Excel\/CSV/));
      });
      await act(async () => {
        fireEvent.press(u.getAllByText(/PDF/)[0]);
      });
      const c = mockIndir.mock.calls.map((x) => [x[0], x[1]]);
      u.unmount();
      return c;
    };
    const tr = await calis();
    expect(tr.length).toBe(2);
    expect(tr[0][1]).toBe("PEMF_Gecmis.csv");
    expect(tr[1][1]).toBe("PEMF_Rapor_3_seans.pdf");
    await enYap();
    expect(await calis()).toEqual(tr);
  });

  it("KRİTİK: tekil silme onayı (başlık / soru / düğme) iki dilde; onay verilmezse istek GİTMEZ", async () => {
    let u = await ekran();
    await act(async () => {
      fireEvent.press(u.getByLabelText("Tekir kaydını sil"));
    });
    expect(platformConfirm).toHaveBeenLastCalledWith("Kaydı Sil", "Bu seans kaydını silmek istediğinizden emin misiniz?", "Sil");
    expect(mockApiPost).not.toHaveBeenCalled();
    u.unmount();
    await enYap();
    u = await ekran();
    await act(async () => {
      fireEvent.press(u.getByLabelText("Delete the record of Tekir"));
    });
    expect(platformConfirm).toHaveBeenLastCalledWith("Delete Record", "Are you sure you want to delete this session record?", "Delete");
    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it("KRİTİK: toplu silme onayı iki dilde; istek gövdesi (id listesi + onay dizgisi) dilden bağımsız", async () => {
    const calis = async (kipEtiketi: string) => {
      (platformConfirm as jest.Mock).mockClear();
      (platformConfirm as jest.Mock).mockResolvedValueOnce(true);
      mockApiPost.mockClear();
      const u = await ekran();
      await act(async () => {
        fireEvent.press(u.getByLabelText(kipEtiketi));
      });
      await act(async () => {
        fireEvent.press(u.getByTestId("gecmis-secim-cubugu-tumunu"));
      });
      await act(async () => {
        fireEvent.press(u.getByTestId("gecmis-secim-cubugu-sil"));
      });
      await act(async () => {});
      const onay = (platformConfirm as jest.Mock).mock.calls.pop();
      const post = mockApiPost.mock.calls.find((c) => c[0] === "/history/delete_bulk");
      u.unmount();
      return { onay, post };
    };
    const tr = await calis("Toplu seçim kipini aç veya kapat");
    expect(tr.onay[0]).toBe("Seçili Kayıtları Sil");
    expect(tr.onay[1]).toContain("3 seans kaydı KALICI olarak silinecek. Bu işlem geri alınamaz.");
    expect(tr.onay[2]).toBe("Sil");
    expect(tr.post?.[1]).toMatchObject({ session_ids: [1, 2, 3] });
    await enYap();
    const en = await calis("Toggle multi-select mode");
    expect(en.onay[0]).toBe("Delete Selected Records");
    expect(en.onay[1]).toContain("3 session records will be PERMANENTLY deleted. This cannot be undone.");
    expect(en.onay[2]).toBe("Delete");
    expect(en.post?.[1]).toEqual(tr.post?.[1]); // veriye giden gövde: EN iken TR ile bayt bayt aynı
  });

  it("daha fazla yükle + dışa aktarım kapsam uyarısı: TR ve EN", async () => {
    mockSeanslar = Array.from({ length: 50 }, (_, i) => KAYIT(i + 1, { patient_name: i === 0 ? "Tekir" : `Hasta${i + 1}` }));
    let u = await ekran();
    expect(metin(u)).toContain("Daha Fazla Yükle");
    expect(u.getByLabelText("Daha fazla geçmiş yükle")).toBeTruthy();
    (platformConfirm as jest.Mock).mockClear();
    await act(async () => {
      fireEvent.press(u.getAllByText(/PDF/)[0]);
    });
    expect(platformConfirm).toHaveBeenLastCalledWith(
      "Yalnızca yüklenen kayıtlar",
      'Şu ana kadar 50 seans yüklendi ve daha fazlası var. Rapor YALNIZ yüklenmiş 50 kaydı içerecek.\n\nTümünü almak için önce "Daha Fazla Yükle" ile listeyi tamamlayın.',
      "Yüklenenleri aktar",
    );
    u.unmount();
    await enYap();
    u = await ekran();
    expect(metin(u)).toContain("Load More");
    expect(u.getByLabelText("Load more history")).toBeTruthy();
    (platformConfirm as jest.Mock).mockClear();
    await act(async () => {
      fireEvent.press(u.getAllByText(/PDF/)[0]);
    });
    expect(platformConfirm).toHaveBeenLastCalledWith(
      "Only loaded records",
      'So far 50 sessions have been loaded and there are more. The report will include ONLY the 50 loaded records.\n\nTo get everything, first complete the list with "Load More".',
      "Export loaded records",
    );
  });

  it("boş liste ve yükleme hatası iletileri iki dilde", async () => {
    mockSeanslar = [];
    let u = render(<TreatmentHistoryScreen />);
    await waitFor(() => expect(metin(u)).toContain("Geçmiş seans kaydı bulunamadı."));
    u.unmount();
    mockSeanslar = null;
    u = render(<TreatmentHistoryScreen />);
    await waitFor(() => expect(metin(u)).toContain("Geçmiş yüklenemedi. Bağlantıyı kontrol edin."));
    expect(metin(u)).toContain("Tekrar Dene");
    u.unmount();
    await enYap();
    u = render(<TreatmentHistoryScreen />);
    await waitFor(() => expect(metin(u)).toContain("History could not be loaded. Check the connection."));
    expect(metin(u)).toContain("Try Again");
    u.unmount();
    mockSeanslar = [];
    u = render(<TreatmentHistoryScreen />);
    await waitFor(() => expect(metin(u)).toContain("No past session records found."));
  });
});

describe("SessionDetailModal", () => {
  const DETAY = (ek: Record<string, unknown> = {}) => ({
    session: {
      id: 7,
      patient_name: "Tekir",
      session_date: "2026-10-01",
      start_time: "10:00",
      end_time: "10:20",
      duration_minutes: 20,
      treatment_mode: "Manuel",
      target_condition: "Eklem",
      operator_name: "Dr. A",
      session_status: "completed",
      patient_notes: "Kontrol",
      ...ek,
    },
    coil_runs: [
      { coil_id: 1, started_epoch: 1_700_000_000, duration_seconds: 125, frequency_hz: 10, duty_percent: 50, hw_type: "stm", summary: { temp_avg: 30, temp_max: 31, field_avg: 1, alan_notu: "×5 düzeltildi" } },
      { coil_id: 8, started_epoch: 1_700_000_000, duration_seconds: 45, frequency_hz: 10, duty_percent: 50, hw_type: "esp" },
    ],
    sensor_samples: [
      { coil_id: 1, sample_ts: 1_700_000_000, temperature_c: 30 },
      { coil_id: 1, sample_ts: 1_700_000_300, temperature_c: 32 },
    ],
  });
  const ac = async () => {
    mockDetay = DETAY();
    const u = render(<SessionDetailModal visible sessionId={7} onClose={() => {}} />);
    await waitFor(() => expect(metin(u)).toContain("Tekir"));
    return metin(u);
  };

  it("TR: başlık, özet etiketleri, bobin tablosu, notlar, uyarılar göç öncesiyle aynı", async () => {
    const m = await ac();
    for (const s of [
      "Seans Detayı",
      "Kapat",
      "Tamamlandı",
      "Tarih",
      "Saat",
      "Süre",
      "20 dk",
      "Mod",
      "Hedef",
      "Operatör",
      "Durum",
      "Notlar",
      "Bobin Çalışmaları",
      "Başlangıç",
      "Frekans",
      "Duty",
      "Şiddet (kayıt)",
      "Alan (ölçülen)",
      "Donanım",
      "Ort. °C",
      "Maks. °C",
      "Bobin 1",
      "Bobin 8",
      "2dk 5sn",
      "45sn",
      "ESP (sökülü)",
      // D6.24 (B-6.11): bayat "STM bobinleri (1-5) … sensörü içermez" notu gerçeğe indirildi (TR DEĞİŞTİ — RAPOR_C1).
      "Not: sıcaklık ve alan yalnız sensör takılı bobinlerde ölçülür; ölçülmeyen değerler boş (—) görünür.",
      "* Alan (ölçülen): ×5 düzeltildi. Eski cihaz yazılımı alanı yaklaşık 5 kat büyük ölçüyordu; özgün değer kayıtta saklıdır.",
      "⚠️ Bu seans, sistemden çıkarılmış ESP donanımına ait satırlar içeriyor (bobin 8 dahil). Sistem 7 bobinlidir; o satırlar GEÇMİŞ kayıttır ve gerçekten uygulandıkları doğrulanmamıştır. Yeni seanslarda bu satırlar oluşmaz.",
      "Sıcaklık Grafiği",
    ]) {
      expect(m).toContain(s);
    }
  });

  it("EN: başlık, özet etiketleri, bobin tablosu, notlar, uyarılar; süre birimleri min / s", async () => {
    await enYap();
    const m = await ac();
    for (const s of [
      "Session Details",
      "Close",
      "Completed",
      "Date",
      "Time",
      "Duration",
      "20 min",
      "Mode",
      "Target",
      "Operator",
      "Status",
      "Notes",
      "Coil Runs",
      "Start",
      "Frequency",
      "Duty",
      "Intensity (recorded)",
      "Field (measured)",
      "Hardware",
      "Avg. °C",
      "Max. °C",
      "Coil 1",
      "Coil 8",
      "2min 5s",
      "45s",
      "ESP (removed)",
      "Note: temperature and field are measured only on coils with a sensor attached; values that were not measured appear empty (—).",
      "* Field (measured): ×5 düzeltildi. The old device firmware measured the field about 5 times too large; the original value is kept in the record.",
      "⚠️ This session contains rows belonging to the ESP hardware that was removed from the system (including coil 8). The system has 7 coils; those rows are HISTORICAL records and it has not been verified that they were actually applied. These rows are not created in new sessions.",
      "Temperature Chart",
    ]) {
      expect(m).toContain(s);
    }
  });

  it("yükleme / yüklenemedi / bilgi yok durumları iki dilde; bilinmeyen durum ham (ilk harf büyük) kalır", async () => {
    mockDetay = null;
    let u = render(<SessionDetailModal visible sessionId={7} onClose={() => {}} />);
    await waitFor(() => expect(metin(u)).toContain("Seans detayları yüklenemedi."));
    u.unmount();
    mockDetay = DETAY({ session_status: "quantum_flux" });
    u = render(<SessionDetailModal visible sessionId={7} onClose={() => {}} />);
    await waitFor(() => expect(metin(u)).toContain("Quantum_flux"));
    u.unmount();
    // [İNCELE] göç öncesi davranış: detay modalının tablosu 13 durumlu (liste ekranında 16); acil durdurma / elektrik kesintisi / donanım reddi
    // modalda ham (ilk harf büyük) görünür — TR birebir kuralı bunu DONDURUR (düzeltme ayrı karar).
    mockDetay = DETAY({ session_status: "emergency_stopped" });
    u = render(<SessionDetailModal visible sessionId={7} onClose={() => {}} />);
    await waitFor(() => expect(metin(u)).toContain("Emergency_stopped"));
    u.unmount();
    await enYap();
    mockDetay = null;
    u = render(<SessionDetailModal visible sessionId={7} onClose={() => {}} />);
    await waitFor(() => expect(metin(u)).toContain("Session details could not be loaded."));
  });
});

describe("dosyaIndir iletileri (gerçek modül)", () => {
  it("TR + EN: kaydedilemedi / indirilemedi / başlatıldı iletileri; dosya adı değişmez", async () => {
    const gercek = jest.requireActual("@/services/dosyaIndir") as typeof import("@/services/dosyaIndir");
    const toast = jest.fn();
    const eskiFetch = (global as any).fetch;
    (global as any).fetch = jest.fn(async () => ({ ok: false, status: 503, headers: { get: () => "" } }));
    // D3.39: düz-HTTP kapısı genel http adrese indirme GÖNDERMEZ — fikstür yerel adres (eskiden "http://x/y", ad = genel host).
    await gercek.downloadFileWithAuth("http://127.0.0.1/y", "PEMF_Gecmis.csv", toast);
    expect(toast).toHaveBeenLastCalledWith("İndirilemedi (503).", "error");
    await enYap();
    await gercek.downloadFileWithAuth("http://127.0.0.1/y", "PEMF_Gecmis.csv", toast);
    expect(toast).toHaveBeenLastCalledWith("Could not be downloaded (503).", "error");
    (global as any).fetch = jest.fn(async () => {
      throw new Error("ag");
    });
    await gercek.downloadFileWithAuth("http://127.0.0.1/y", "PEMF_Gecmis.csv", toast);
    expect(toast).toHaveBeenLastCalledWith("An error occurred during the download.", "error");
    (global as any).fetch = eskiFetch;
    expect(i18n.language).toBe("en");
  });
});
