// Author: mertaygn, cglrgrkn
/**
 * Y308 (sahip 19-11: "konum kaydını da al yayına ama sensör serbest de gezdirilebilsin konum bilgisi olmadan; kullanıcı hangisini isterse").
 * SÖZLEŞME (arayüz):
 *   - seans YOKKEN kabin sensörü kartında konum düğmesi YOK; seans sürerken "Sensör konumu" → satır içi form (sol / ön çıkıntıdan,
 *     tabandan cm + not; TR virgül kabul) → `/session/sensor_konumu`; önceki konum varsa düğme "Sensörü taşıdım"; "Serbest" konumsuz giriş;
 *   - sunucunun eylem söyleyen hata metni formda görünür, kayıt yapılmadı sayılır;
 *   - seans detayı: girişler varsa dilimler (konum, süre, ort / en yüksek mT, model tahmini + fark — dile göre; serbestte tahmin yok);
 *     giriş + kabin alanı yoksa bölüm HİÇ yok (ekran birebir); seans sonrası ekleme başlangıç saatiyle (`zamanEpoch`), düzeltme = ekle +
 *     eskisini sil, sonra detay yeniden yüklenir. TR + EN.
 * GERÇEK: KabinSensoruKarti, SensorKonumuFormu, KonumDilimleriBolumu, SessionDetailModal, katalog; sahte: apiClient + canlı veri bağlamı.
 */
import React from "react";
import { act, fireEvent, render, waitFor, within } from "@testing-library/react-native";

const mockApiGet = jest.fn();
const mockApiPost = jest.fn();
const mockApiDelete = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: (...a: unknown[]) => mockApiPost(...a),
  apiDelete: (...a: unknown[]) => mockApiDelete(...a),
  platformAlert: jest.fn(),
}));
let mockSnap: unknown = null;
jest.mock("@/context/LiveDataContext", () => ({ useLiveData: () => ({ snapshot: mockSnap }) }));

import { KabinSensoruKarti } from "@/components/domain/KabinSensoruKarti";
import { SessionDetailModal } from "@/components/domain/SessionDetailModal";
import { saattenEpoch } from "@/components/domain/SensorKonumuFormu";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const depo = { setItem: async () => undefined };
const SEANS_BAS = new Date(2026, 10, 19, 18, 7, 0).getTime() / 1000;

beforeEach(() => {
  mockApiGet.mockReset();
  mockApiPost.mockReset();
  mockApiDelete.mockReset();
});
afterEach(async () => {
  mockSnap = null;
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

async function dil(d: "tr" | "en") {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec(d, depo);
  });
}

it("KRİTİK seans YOKKEN konum düğmesi YOK (kart yalnız ölçüm)", () => {
  mockSnap = { coils: [{ id: 6, magneticMt: 1.3, measuredFields: ["magneticMt"] }] };
  const u = render(<KabinSensoruKarti />);
  expect(u.queryByTestId("kabin-sensoru-konum-dugmesi")).toBeNull();
  expect(mockApiGet).not.toHaveBeenCalled();
});

it("KRİTİK seans sürerken: serbest durum → form → konumlu kayıt (TR virgül) → 'Sensörü taşıdım' ve konum özeti", async () => {
  mockSnap = { activeTreatment: { isActive: true }, coils: [] };
  mockApiGet.mockResolvedValueOnce({ aktif: true, konum: null });
  const u = render(<KabinSensoruKarti />);
  await waitFor(() => expect(u.getByTestId("kabin-sensoru-konum").props.children).toBe("Konum: serbest (girilmedi)"));
  expect(mockApiGet).toHaveBeenCalledWith("/session/sensor_konumu", null, { silent: true });
  fireEvent.press(u.getByTestId("kabin-sensoru-konum-dugmesi"));
  fireEvent.changeText(u.getByTestId("sensor-konumu-sol"), "27");
  fireEvent.changeText(u.getByTestId("sensor-konumu-on"), "20");
  fireEvent.changeText(u.getByTestId("sensor-konumu-yukseklik"), "2,5");
  fireEvent.changeText(u.getByTestId("sensor-konumu-not"), " plaka yanı ");
  expect(u.getByText("Konumu kaydet")).toBeTruthy();
  mockApiPost.mockResolvedValueOnce({ status: "success", id: 1 });
  mockApiGet.mockResolvedValueOnce({
    aktif: true,
    konum: { id: 1, zaman_epoch: SEANS_BAS + 60, serbest: false, sol_cm: 27, on_cm: 20, yukseklik_cm: 2.5, not_metni: "plaka yanı" },
  });
  await act(async () => {
    fireEvent.press(u.getByTestId("sensor-konumu-kaydet"));
  });
  expect(mockApiPost.mock.calls[0][0]).toBe("/session/sensor_konumu");
  expect(mockApiPost.mock.calls[0][1]).toEqual({ serbest: false, solCm: 27, onCm: 20, yukseklikCm: 2.5, notMetni: "plaka yanı" });
  await waitFor(() =>
    expect(u.getByTestId("kabin-sensoru-konum").props.children).toBe("Konum: sol 27 cm · ön 20 cm · yükseklik 2,5 cm"),
  );
  expect(u.queryByTestId("sensor-konumu-formu")).toBeNull();
  fireEvent.press(u.getByTestId("kabin-sensoru-konum-dugmesi"));
  expect(u.getByText("Sensörü taşıdım — kaydet")).toBeTruthy();
});

it("KRİTİK 'Serbest' konumsuz giriş; sunucu hatası formda görünür (kayıt yok sayılır)", async () => {
  mockSnap = { activeTreatment: { isActive: true }, coils: [] };
  mockApiGet.mockResolvedValue({ aktif: true, konum: null });
  const u = render(<KabinSensoruKarti />);
  await waitFor(() => expect(u.getByTestId("kabin-sensoru-konum-dugmesi")).toBeTruthy());
  fireEvent.press(u.getByTestId("kabin-sensoru-konum-dugmesi"));
  mockApiPost.mockImplementationOnce(async (_p: string, _b: unknown, f: unknown, o: { onHttpError: (s: number, d?: string) => void }) => {
    o.onHttpError(422, "Sensör konumu geçersiz: …");
    return f;
  });
  fireEvent.changeText(u.getByTestId("sensor-konumu-sol"), "500");
  await act(async () => {
    fireEvent.press(u.getByTestId("sensor-konumu-kaydet"));
  });
  expect(u.getByTestId("sensor-konumu-hata").props.children).toBe("Sensör konumu geçersiz: …");
  mockApiPost.mockResolvedValueOnce({ status: "success" });
  await act(async () => {
    fireEvent.press(u.getByTestId("sensor-konumu-serbest"));
  });
  expect(mockApiPost.mock.calls[1][1]).toEqual({ serbest: true, notMetni: "" });
  await waitFor(() => expect(u.queryByTestId("sensor-konumu-formu")).toBeNull());
  // vazgeç formu kapatır, istek yok
  fireEvent.press(u.getByTestId("kabin-sensoru-konum-dugmesi"));
  fireEvent.press(u.getByTestId("sensor-konumu-vazgec"));
  expect(u.queryByTestId("sensor-konumu-formu")).toBeNull();
  // hata metni gelmezse genel metin
  fireEvent.press(u.getByTestId("kabin-sensoru-konum-dugmesi"));
  mockApiPost.mockResolvedValueOnce(null);
  await act(async () => {
    fireEvent.press(u.getByTestId("sensor-konumu-serbest"));
  });
  expect(u.getByTestId("sensor-konumu-hata").props.children).toBe("Konum kaydedilemedi — bağlantıyı denetleyip yeniden deneyin.");
});

// ── seans detayı ───────────────────────────────────────────────────────────────────────────────────────────────────────
const seans = { id: 9, patient_name: "Plaka 1", session_date: "2026-11-19", start_time: "18:07", started_epoch: SEANS_BAS,
  ended_epoch: SEANS_BAS + 600, duration_minutes: 10, treatment_mode: "AI Pro · Petri Kuyu", session_status: "stopped" };
const mlx = [{ coil_id: "6", sample_ts: SEANS_BAS + 60, magnetic_field_mt: 1.3 }];
const giris = { id: 5, zaman_epoch: SEANS_BAS + 120, serbest: false, sol_cm: 27, on_cm: 20, yukseklik_cm: 2.5, not_metni: "A1" };
const dilimler = [
  { baslangic_epoch: SEANS_BAS, bitis_epoch: SEANS_BAS + 120, sure_sn: 120, serbest: true, kayit_id: null, sol_cm: null, on_cm: null,
    yukseklik_cm: null, not: "", olcum_sayisi: 1, ortalama_mt: 1.3, tepe_mt: 1.3, tahmin_mt: null, fark_yuzde: null },
  { baslangic_epoch: SEANS_BAS + 120, bitis_epoch: SEANS_BAS + 600, sure_sn: 480, serbest: false, kayit_id: 5, sol_cm: 27, on_cm: 20,
    yukseklik_cm: 2.5, not: "A1", olcum_sayisi: 8, ortalama_mt: 1.32, tepe_mt: 1.38, tahmin_mt: 1.2, fark_yuzde: 10 },
];

async function detay(veri: Record<string, unknown>) {
  mockApiGet.mockResolvedValue({ session: seans, coil_runs: [], ...veri });
  const u = render(<SessionDetailModal visible sessionId={9} onClose={() => {}} />);
  await waitFor(() => expect(mockApiGet).toHaveBeenCalledWith("/history/9/details", null));
  await waitFor(() => expect(u.queryByText("Seans bilgisi bulunamadı")).toBeNull());
  return u;
}

it("KARŞIT giriş YOK + kabin alanı YOK → konum bölümü HİÇ yok (ekran birebir)", async () => {
  const u = await detay({ sensor_samples: [] });
  await waitFor(() => expect(u.getByTestId("seans-alan-bolumu")).toBeTruthy());
  expect(u.queryByTestId("seans-konum-bolumu")).toBeNull();
});

it("KRİTİK dilimler: konum, süre, ölçülen, model tahmini + fark (TR %10,0), serbest dilimde tahmin YOK", async () => {
  const u = await detay({ sensor_samples: mlx, sensor_konumlari: [giris], konum_dilimleri: dilimler });
  await waitFor(() => expect(u.getByTestId("seans-konum-bolumu")).toBeTruthy());
  const d0 = within(u.getByTestId("konum-dilimi-0"));
  expect(d0.getByText(/2 dk 0 sn/)).toBeTruthy();
  expect(u.getByTestId("konum-dilimi-tahmin-0").props.children).toBe("Serbest dilim — model tahmini yok.");
  const d1 = within(u.getByTestId("konum-dilimi-1"));
  expect(d1.getByText(/Konum: sol 27 cm · ön 20 cm · yükseklik 2,5 cm/)).toBeTruthy();
  expect(d1.getByText("Ölçülen: ort. 1,32 mT · en yüksek 1,38 mT")).toBeTruthy();
  expect(u.getByTestId("konum-dilimi-tahmin-1").props.children).toBe("Model tahmini (aynı nokta, aynı sürüş): 1,20 mT · fark %10,0");
  expect(d1.getByText("A1")).toBeTruthy();
});

it("KRİTİK seans SONRASI ekleme: başlangıç saati seçilir (zamanEpoch), kayıttan sonra detay YENİDEN yüklenir", async () => {
  const u = await detay({ sensor_samples: mlx });
  await waitFor(() => expect(u.getByTestId("seans-konum-ekle")).toBeTruthy());
  fireEvent.press(u.getByTestId("seans-konum-ekle"));
  expect(u.getByTestId("sensor-konumu-saat").props.value).toBe("18:07:00");
  fireEvent.changeText(u.getByTestId("sensor-konumu-saat"), "25:00");
  await act(async () => {
    fireEvent.press(u.getByTestId("sensor-konumu-serbest"));
  });
  expect(u.getByTestId("sensor-konumu-hata").props.children).toBe("Saati SS:DD:ss biçiminde girin (ör. 18:07:30).");
  expect(mockApiPost).not.toHaveBeenCalled();
  fireEvent.changeText(u.getByTestId("sensor-konumu-saat"), "18:07:30");
  fireEvent.changeText(u.getByTestId("sensor-konumu-sol"), "10");
  fireEvent.changeText(u.getByTestId("sensor-konumu-on"), "5");
  fireEvent.changeText(u.getByTestId("sensor-konumu-yukseklik"), "3");
  mockApiPost.mockResolvedValueOnce({ status: "success", id: 6 });
  const once = mockApiGet.mock.calls.length;
  await act(async () => {
    fireEvent.press(u.getByTestId("sensor-konumu-kaydet"));
  });
  expect(mockApiPost.mock.calls[0][0]).toBe("/history/9/sensor_konumu");
  expect(mockApiPost.mock.calls[0][1]).toEqual({ serbest: false, solCm: 10, onCm: 5, yukseklikCm: 3, notMetni: "", zamanEpoch: SEANS_BAS + 30 });
  await waitFor(() => expect(mockApiGet.mock.calls.length).toBeGreaterThan(once));
});

it("KRİTİK düzeltme = yeni giriş + eskisinin silinmesi (önce ekle); silme düğmesi siler ve yeniden yükler", async () => {
  const u = await detay({ sensor_samples: mlx, sensor_konumlari: [giris], konum_dilimleri: dilimler });
  await waitFor(() => expect(u.getByTestId("konum-duzelt-5")).toBeTruthy());
  fireEvent.press(u.getByTestId("konum-duzelt-5"));
  expect(u.getByTestId("sensor-konumu-sol").props.value).toBe("27");
  expect(u.getByTestId("sensor-konumu-saat").props.value).toBe("18:09:00");
  fireEvent.changeText(u.getByTestId("sensor-konumu-sol"), "28");
  mockApiPost.mockResolvedValueOnce({ status: "success", id: 7 });
  mockApiDelete.mockResolvedValue({ status: "success" });
  await act(async () => {
    fireEvent.press(u.getByTestId("sensor-konumu-kaydet"));
  });
  expect(mockApiPost.mock.calls[0][1]).toMatchObject({ solCm: 28, zamanEpoch: SEANS_BAS + 120, notMetni: "A1" });
  expect(mockApiDelete).toHaveBeenCalledWith("/history/9/sensor_konumu/5", null);
  await waitFor(() => expect(u.getByTestId("konum-sil-5")).toBeTruthy());
  const once = mockApiGet.mock.calls.length;
  await act(async () => {
    fireEvent.press(u.getByTestId("konum-sil-5"));
  });
  await waitFor(() => expect(mockApiGet.mock.calls.length).toBeGreaterThan(once));
});

it("EN: kart ve dilim metinleri İngilizce, ondalık nokta, fark '10.0%'", async () => {
  await dil("en");
  const u = await detay({ sensor_samples: mlx, sensor_konumlari: [giris], konum_dilimleri: dilimler });
  await waitFor(() => expect(u.getByTestId("seans-konum-bolumu")).toBeTruthy());
  expect(u.getByText("Cabin sensor position slices")).toBeTruthy();
  expect(u.getByTestId("konum-dilimi-tahmin-1").props.children).toBe("Model estimate (same point, same drive): 1.20 mT · difference 10.0%");
  expect(within(u.getByTestId("konum-dilimi-1")).getByText(/Position: left 27 cm · front 20 cm · height 2.5 cm/)).toBeTruthy();
});

it("saattenEpoch: geçersiz biçim / aralık null; saniyesiz kabul", () => {
  expect(saattenEpoch("18:07", SEANS_BAS)).toBe(SEANS_BAS);
  expect(saattenEpoch("18:07:30", SEANS_BAS)).toBe(SEANS_BAS + 30);
  expect(["", "x", "24:00", "18:60", "18:07:61", "1807"].map((s) => saattenEpoch(s, SEANS_BAS))).toEqual([null, null, null, null, null, null]);
});

it("kenar: GET boş yanıt → serbest durum; durum kodlu hata metni (ayrıntısız) formda", async () => {
  mockSnap = { activeTreatment: { isActive: true }, coils: [] };
  mockApiGet.mockResolvedValue(null);
  const u = render(<KabinSensoruKarti />);
  await waitFor(() => expect(u.getByTestId("kabin-sensoru-konum").props.children).toBe("Konum: serbest (girilmedi)"));
  fireEvent.press(u.getByTestId("kabin-sensoru-konum-dugmesi"));
  mockApiPost.mockImplementationOnce(async (_p: string, _b: unknown, f: unknown, o: { onHttpError: (s: number, d?: string) => void }) => {
    o.onHttpError(500);
    return f;
  });
  await act(async () => {
    fireEvent.press(u.getByTestId("sensor-konumu-serbest"));
  });
  expect(u.getByTestId("sensor-konumu-hata").props.children).toBe("500");
});

it("kenar: başlangıcı bilinmeyen seans (taban ilk girişten), farksız dilim '—', kabin alanı yokken girişler yine görünür; kayıt hatası / vazgeç / silme hatası", async () => {
  const seansSiz = { ...seans, started_epoch: undefined };
  const dilim = { ...dilimler[1], fark_yuzde: null, not: "" };
  mockApiGet.mockResolvedValue({ session: seansSiz, coil_runs: [], sensor_samples: [], sensor_konumlari: [giris], konum_dilimleri: [dilim] });
  const u = render(<SessionDetailModal visible sessionId={9} onClose={() => {}} />);
  await waitFor(() => expect(u.getByTestId("seans-konum-bolumu")).toBeTruthy());
  expect(u.getByTestId("konum-dilimi-tahmin-0").props.children).toBe("Model tahmini (aynı nokta, aynı sürüş): 1,20 mT · fark —");
  fireEvent.press(u.getByTestId("seans-konum-ekle"));
  expect(u.getByTestId("sensor-konumu-saat").props.value).toBe("18:09:00"); // taban = ilk girişin zamanı
  mockApiPost.mockResolvedValueOnce(null);
  await act(async () => {
    fireEvent.press(u.getByTestId("sensor-konumu-serbest"));
  });
  expect(u.getByTestId("sensor-konumu-hata").props.children).toBe("Konum kaydedilemedi — bağlantıyı denetleyip yeniden deneyin.");
  fireEvent.press(u.getByTestId("sensor-konumu-vazgec"));
  expect(u.queryByTestId("seans-konum-formu")).toBeNull();
  mockApiDelete.mockResolvedValueOnce(null);
  const once = mockApiGet.mock.calls.length;
  await act(async () => {
    fireEvent.press(u.getByTestId("konum-sil-5"));
  });
  expect(mockApiGet.mock.calls.length).toBe(once); // silme düştü → yeniden yükleme yok
});

it("kenar: seans değişirken ESKİ seansın konumları yeni seansta GÖRÜNMEZ", async () => {
  mockApiGet.mockResolvedValueOnce({ session: seans, coil_runs: [], sensor_samples: mlx, sensor_konumlari: [giris], konum_dilimleri: dilimler });
  const u = render(<SessionDetailModal visible sessionId={9} onClose={() => {}} />);
  await waitFor(() => expect(u.getByTestId("seans-konum-bolumu")).toBeTruthy());
  mockApiGet.mockImplementationOnce(() => new Promise(() => undefined));
  u.rerender(<SessionDetailModal visible sessionId={10} onClose={() => {}} />);
  expect(u.queryByTestId("konum-girisi-5")).toBeNull();
});

it("kenar: başlangıç da giriş de yoksa taban şimdiki zaman", async () => {
  mockApiGet.mockResolvedValue({ session: { ...seans, started_epoch: undefined }, coil_runs: [], sensor_samples: mlx });
  const u = render(<SessionDetailModal visible sessionId={9} onClose={() => {}} />);
  await waitFor(() => expect(u.getByTestId("seans-konum-ekle")).toBeTruthy());
  fireEvent.press(u.getByTestId("seans-konum-ekle"));
  expect(u.getByTestId("sensor-konumu-saat").props.value).toMatch(/^\d{2}:\d{2}:\d{2}$/);
});

it("kenar: konumlu dilimde ölçüm ve tahmin yoksa '—' ve 'Model tahmini yok (…)'", async () => {
  const d = { ...dilimler[1], ortalama_mt: null, tepe_mt: null, tahmin_mt: null, fark_yuzde: null };
  mockApiGet.mockResolvedValue({ session: seans, coil_runs: [], sensor_samples: mlx, sensor_konumlari: [giris], konum_dilimleri: [d] });
  const u = render(<SessionDetailModal visible sessionId={9} onClose={() => {}} />);
  await waitFor(() => expect(u.getByTestId("seans-konum-bolumu")).toBeTruthy());
  expect(within(u.getByTestId("konum-dilimi-0")).getByText("Ölçülen: ort. — mT · en yüksek — mT")).toBeTruthy();
  expect(u.getByTestId("konum-dilimi-tahmin-0").props.children).toBe(
    "Model tahmini yok (kabin kalibrasyonu ya da alan modeli yok, ya da o dilimde sürüş yok).",
  );
});

it("kenar: seans sonrası girişte sunucunun eylem söyleyen hata metni (zaman dışı) formda görünür", async () => {
  mockApiGet.mockResolvedValue({ session: seans, coil_runs: [], sensor_samples: mlx });
  const u = render(<SessionDetailModal visible sessionId={9} onClose={() => {}} />);
  await waitFor(() => expect(u.getByTestId("seans-konum-ekle")).toBeTruthy());
  fireEvent.press(u.getByTestId("seans-konum-ekle"));
  mockApiPost.mockImplementationOnce(async (_p: string, _b: unknown, f: unknown, o: { onHttpError: (s: number, d?: string) => void }) => {
    o.onHttpError(422, "Konumun başlangıç saati seansın başlangıç–bitiş aralığında olmalı.");
    return f;
  });
  await act(async () => {
    fireEvent.press(u.getByTestId("sensor-konumu-serbest"));
  });
  expect(u.getByTestId("sensor-konumu-hata").props.children).toBe("Konumun başlangıç saati seansın başlangıç–bitiş aralığında olmalı.");
});
