// Author: mertaygn, cglrgrkn
/**
 * D6.24 (B-6.11) — Seans Detayı'ndaki bayat "STM bobinleri (1-5) … sensörü içermez" notları kalkar; not GERÇEK kablolamayı söyler.
 * =================================================================================================================================
 * ÖLÇÜLEN KUSUR (HEAD ebf1c3fe): tablo altı notu her seansta "Not: STM bobinleri (1-5) gerçek donanımda sıcaklık/akım/alan sensörü
 * içermez" diyordu; sıcaklık bölümü boşken "(gerçek STM bobinleri sıcaklık sensörü içermez)". Gerçek (kod): sistem 7 bobinin HEPSİNİ
 * STM'den sürer; sıcaklık / alan sensörleri yalnız sensör takılı bobinden gelir (`firmware/stm32_pemf/Core/Inc/pemf_sensor.h`
 * `PEMF_SENSOR_BOBIN_IDLERI {6U, 6U}` — bugün bobin 6: MLX90393 alan + takılırsa sıcaklık); bobin 1-5'te akım (ACS712) satırı VAR ama
 * Y154 gereği hiçbir kayda yazılmaz ve gösterilmez (`headless_core.py` CH4 · Y154). "1-5 sensör içermez" hem bobin aralığında hem
 * akımda yanlıştı ve ölçülmüş bobin 6 sıcaklığını / alanını gösteren seansta da çıkıyordu.
 * Veri ELLE YAZILMADI: GERÇEK `/api/history/{id}/details` yanıtları — `__fixtures__/alanDuzeltme.CH3.json` (bobin 6 sıcaklık + alan;
 * sıcaklıksız yeni seans) ve `__fixtures__/kayitGorunumu.D189.json` (bobin 1-2 STM koşusu); bayatlık kapıları
 * tests/test_CH3_gecmis_mT_BOLU5_Y152.py, tests/test_D189_kayit_gorunumu_RECETE_kayit_OLCULEN_ayri.py.
 * GERÇEK: SessionDetailModal + katalog; sahte yalnız `apiClient.apiGet` (ağ sınırı).
 */
import React from "react";
import { render, waitFor } from "@testing-library/react-native";
import { EN, TR } from "@/i18n/__tests__/kaynakMetni";

const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(),
  platformAlert: jest.fn(),
}));

import { SessionDetailModal } from "@/components/domain/SessionDetailModal";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const CH3: any = require("../../../screens/__tests__/__fixtures__/alanDuzeltme.CH3.json");
// eslint-disable-next-line @typescript-eslint/no-var-requires
const D189: any = require("../../../screens/__tests__/__fixtures__/kayitGorunumu.D189.json");

function metin(d: any): string {
  if (d == null || typeof d === "boolean") return "";
  if (typeof d === "string" || typeof d === "number") return String(d);
  if (Array.isArray(d)) return d.map(metin).join("");
  return (d.children || []).map(metin).join("");
}

async function ciz(detay: { session: { id: number }; coil_runs: Array<{ coil_id: number }> }): Promise<string> {
  mockApiGet.mockReset();
  mockApiGet.mockResolvedValue(detay);
  // Modal yalnız GÜNCEL oturumun detayını çizer (`session.id` eşleşmesi) — kimlik yanıttan.
  const u = render(<SessionDetailModal visible sessionId={detay.session.id} onClose={() => {}} />);
  const ilk = detay.coil_runs[0].coil_id;
  await waitFor(() => expect(u.queryByTestId(`seans-bobin-olculen-alan-${ilk}`)).not.toBeNull());
  const m = metin(u.toJSON());
  u.unmount();
  return m;
}

/** Bayat iddianın her biçimi (TR + EN) — yokluk ölçütü. */
const BAYAT = [/\(1-5\)/, /içermez/, /have no temperature/, /no temperature\/current\/field sensor/];
const NOT_TR = "Not: sıcaklık ve alan yalnız sensör takılı bobinlerde ölçülür; ölçülmeyen değerler boş (—) görünür.";
const BOS_TR = "Bu seansta sıcaklık ölçümü yok (sıcaklık yalnız sensör takılı bobinlerde ölçülür).";

it("KRİTİK: bobin 6 sıcaklık + alan ÖLÇÜLMÜŞ seans — bayat '1-5 … sensörü içermez' notu YOK, gerçek not VAR", async () => {
  expect(CH3.eski.coil_runs[0].summary.temp_avg).toBe(30.5); // ARA: GERÇEK yanıtta ölçülmüş sıcaklık
  const m = await ciz(CH3.eski);
  expect(m).toContain("30.5"); // ölçülen sıcaklık tabloda
  for (const b of BAYAT) expect(m).not.toMatch(b);
  expect(m).toContain(NOT_TR);
});

it("KRİTİK: sıcaklık örneği olmayan seans — boş bölüm notu 'STM bobinleri sıcaklık sensörü içermez' DEMEZ", async () => {
  expect(CH3.yeni.sensor_samples).toEqual([]); // ARA: GERÇEK yanıtta sıcaklık örneği yok
  const m = await ciz(CH3.yeni);
  for (const b of BAYAT) expect(m).not.toMatch(b);
  expect(m).toContain(BOS_TR);
});

it("KARŞIT (Y154): bobin 1-2 STM koşusu — not bayat değil; akım sütunu / değeri gösterilmez", async () => {
  const m = await ciz(D189.detay);
  for (const b of BAYAT) expect(m).not.toMatch(b);
  expect(m).toContain(NOT_TR);
  expect(m).not.toMatch(/\d\s?A\b/); // akım (A) hiçbir hücrede yok
});

it("KATALOG: TR birebir, EN dolu ve bayat iddia iki dilde de yok", () => {
  expect(TR["seans.detay.stmNotu"]).toBe(NOT_TR);
  expect(TR["seans.detay.sensorVerisiYok"]).toBe(BOS_TR);
  expect(EN["seans.detay.stmNotu"]).toBe(
    "Note: temperature and field are measured only on coils with a sensor attached; values that were not measured appear empty (—).",
  );
  expect(EN["seans.detay.sensorVerisiYok"]).toBe(
    "There is no temperature measurement for this session (temperature is measured only on coils with a sensor attached).",
  );
  for (const k of ["seans.detay.stmNotu", "seans.detay.sensorVerisiYok"]) {
    for (const b of BAYAT) {
      expect(TR[k]).not.toMatch(b);
      expect(EN[k]).not.toMatch(b);
    }
  }
});

// TUR 2 (çürütücü kolu): "Bu seansta sıcaklık ölçümü yok" kesin bir iddiadır — TEK bir gerçek sıcaklık örneği de ölçümdür. Eşiği 2 örneğe
// çıkaran mutant (`cur624_n1`) üç kapıda da YAŞIYORDU (fikstürlerde örnek ya 0 ya ≥ 3).
it("SINIR (tur 2): TEK sıcaklık örneği olan seans — 'sıcaklık ölçümü yok' notu ÇİZİLMEZ", async () => {
  const tek = JSON.parse(JSON.stringify(CH3.eski));
  tek.sensor_samples = tek.sensor_samples.filter((s: { temperature_c: unknown }) => s.temperature_c != null).slice(0, 1);
  expect(tek.sensor_samples).toHaveLength(1); // ARA: GERÇEK satır şekli, tek sıcaklık örneği
  const m = await ciz(tek);
  expect(m).not.toContain(BOS_TR);
  expect(m).toContain(NOT_TR);
});
