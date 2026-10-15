// Author: mertaygn, cglrgrkn
/**
 * CH3 · Y152 (sahip 2026-10-15) — geçmiş seansın ÷5 düzeltilmiş ölçülen alanı EKRANDA notla görünür.
 * =================================================================================================
 * ÖLÇÜLEN DURUM (taban `f4f07422`): Seans Detayı "Alan (ölçülen)" sütunu TD2 öncesi firmware'in ~5× ölçtüğü değeri notsuz gösteriyordu.
 * SÖZLEŞME: backend göçü eski kaydı ÷5 düzeltir, orijinali saklar ve `summary.alan_notu`'yu verir (tek kaynak
 * `apps/backend/utils/mt_duzeltme.NOT_METNI`); arayüz değeri " *" ile işaretler ve tablonun altında notu NEDEN + KAPSAM ile söyler.
 * Yeni (TD2 sonrası) seansta not ÇIKMAZ.
 * Veri ELLE YAZILMADI: `__fixtures__/alanDuzeltme.CH3.json` GERÇEK `/api/history/{id}/details` yanıtından üretilir (bayatlık kapısı
 * `tests/test_CH3_gecmis_mT_BOLU5_Y152.py::test_arayuz_fiksturu_GERCEK_yanitla_AYNI`).
 * ⚠️ MUTASYON: not çizilmezse, yıldız düşerse ya da not her seansta çıkarsa KIRMIZI.
 */
import React from "react";
import { render, waitFor } from "@testing-library/react-native";

const mockApiGet = jest.fn();
jest.mock("@/services/apiClient", () => ({
  apiGet: (...a: unknown[]) => mockApiGet(...a),
  apiPost: jest.fn(),
  platformAlert: jest.fn(),
}));

import { SessionDetailModal } from "@/components/domain/SessionDetailModal";

const F: any = require("./__fixtures__/alanDuzeltme.CH3.json");

async function ciz(detay: unknown) {
  mockApiGet.mockReset();
  mockApiGet.mockResolvedValue(detay);
  const u = render(<SessionDetailModal visible sessionId={7} onClose={() => {}} />);
  await waitFor(() => expect(u.queryByTestId("seans-bobin-olculen-alan-6")).not.toBeNull());
  return u;
}

function metin(d: any): string {
  if (d == null || typeof d === "boolean") return "";
  if (typeof d === "string" || typeof d === "number") return String(d);
  if (Array.isArray(d)) return d.map(metin).join("");
  return (d.children || []).map(metin).join("");
}

it("KRİTİK eski (göç edilmiş) seans: değer düzeltilmiş + yıldızlı, not NEDEN ve kapsamla çizilir", async () => {
  const u = await ciz(F.eski);
  const hucre = metin(u.getByTestId("seans-bobin-olculen-alan-6").props.children);
  expect(hucre).toMatch(/2\.33 mT/);
  expect(hucre).toContain("*");
  const not = metin(u.getByTestId("seans-alan-duzeltme-notu").props.children);
  expect(not).toContain(F.eski.coil_runs[0].summary.alan_notu); // backend metni AYNEN (tek kaynak)
  expect(not).toMatch(/÷5/);
  expect(not).toMatch(/özgün değer kayıtta saklıdır/);
});

it("KARŞIT yeni (TD2 sonrası) seans: not YOK, yıldız YOK", async () => {
  const u = await ciz(F.yeni);
  const hucre = metin(u.getByTestId("seans-bobin-olculen-alan-6").props.children);
  expect(hucre).toMatch(/2\.50 mT/);
  expect(hucre).not.toContain("*");
  expect(u.queryByTestId("seans-alan-duzeltme-notu")).toBeNull();
});
