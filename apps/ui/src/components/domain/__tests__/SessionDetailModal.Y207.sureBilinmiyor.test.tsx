// Author: mertaygn, cglrgrkn
/**
 * Y207 (S-D5.3) — kanıtı 3 açılış boyunca okunamayan seans "süre bilinmiyor" (`ABORTED_DURATION_UNKNOWN`) kapanır; Seans Detayı durumu
 * çevrilmiş etiketle gösterir ve süre / dozun uydurulmadığını AÇIKLAR (TR + EN). Süre hücresi boş (—) — tahmini değer yazılmaz.
 * Veri: GERÇEK `/api/history/{id}/details` yanıtı (`__fixtures__/alanDuzeltme.CH3.json`) — yalnız durum ve süre alanı sunucunun yeni
 * kapanış mührüne çevrildi (`recover_stale_active_sessions`: `session_status = ABORTED_DURATION_UNKNOWN`, `duration_minutes = NULL`).
 * Kapı (sunucu): tests/test_acilis_kurtarmasi_KANIT_3_acilista_SURE_BILINMIYOR_Y207.py. GERÇEK: SessionDetailModal + katalog; sahte yalnız `apiGet`.
 */
import React from "react";
import { act, render, waitFor } from "@testing-library/react-native";
import { EN, TR } from "@/i18n/__tests__/kaynakMetni";
import { __bayrakTestiAyarla } from "@/i18n/dil";
import { dilSec } from "@/i18n";

const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(),
  platformAlert: jest.fn(),
}));

import { SessionDetailModal } from "@/components/domain/SessionDetailModal";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const CH3: any = require("../../../screens/__tests__/__fixtures__/alanDuzeltme.CH3.json");

const depo = { setItem: async () => undefined };

afterEach(async () => {
  __bayrakTestiAyarla(null);
  await act(async () => {
    await dilSec("tr", depo);
  });
});

function metin(d: any): string {
  if (d == null || typeof d === "boolean") return "";
  if (typeof d === "string" || typeof d === "number") return String(d);
  if (Array.isArray(d)) return d.map(metin).join("");
  return (d.children || []).map(metin).join("");
}

function detay(durum: string, sure: number | null) {
  const d = JSON.parse(JSON.stringify(CH3.eski));
  d.session.session_status = durum;
  d.session.duration_minutes = sure;
  return d;
}

async function ciz(d: any): Promise<{ m: string; not: boolean }> {
  mockApiGet.mockReset();
  mockApiGet.mockResolvedValue(d);
  const u = render(<SessionDetailModal visible sessionId={d.session.id} onClose={() => {}} />);
  const ilk = d.coil_runs[0].coil_id;
  await waitFor(() => expect(u.queryByTestId(`seans-bobin-olculen-alan-${ilk}`)).not.toBeNull());
  const not = u.queryByTestId("seans-sure-bilinmiyor-notu") !== null;
  const m = metin(u.toJSON());
  u.unmount();
  return { m, not };
}

it("KRİTİK: 'süre bilinmiyor' seansı — durum ÇEVRİLMİŞ etiket, açıklama notu VAR, ham durum adı YOK (TR)", async () => {
  const { m, not } = await ciz(detay("ABORTED_DURATION_UNKNOWN", null));
  expect(not).toBe(true);
  expect(m).toContain(TR["seans.durum.aborted_duration_unknown"]);
  expect(m).toContain(TR["seans.detay.sureBilinmiyorNotu"]);
  expect(m).not.toMatch(/Aborted_duration_unknown|ABORTED_DURATION_UNKNOWN/);
});

it("KRİTİK: aynı seans İngilizce — etiket ve not EN; Türkçe metin kalmaz", async () => {
  __bayrakTestiAyarla(true);
  await act(async () => {
    await dilSec("en", depo);
  });
  const { m, not } = await ciz(detay("ABORTED_DURATION_UNKNOWN", null));
  expect(not).toBe(true);
  expect(m).toContain(EN["seans.durum.aborted_duration_unknown"]);
  expect(m).toContain(EN["seans.detay.sureBilinmiyorNotu"]);
  expect(m).not.toContain(TR["seans.detay.sureBilinmiyorNotu"]);
});

it("KARŞIT: kanıtla kapanmış seans (Elektrik Kesintisi / Tamamlandı) — not YOK", async () => {
  for (const durum of ["ABORTED_DUE_TO_POWER", "completed"]) {
    const { not } = await ciz(detay(durum, 8));
    expect(not).toBe(false);
  }
});
