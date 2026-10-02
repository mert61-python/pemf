// Author: mertaygn, cglrgrkn
/**
 * D1.E09 (İG-5.31) · 1-D inceleme i3-F-8 — AI Geçmişi detayında örtü alanı Türkçe etiketle görünür.
 * Ölçülen kusur: `detailRows` landmark yanıtındaki `nokta_gorunurlugu_dogrulanmadi` için ham değişken adını basıyordu
 * (hekim geçmişte "nokta_gorunurlugu_dogrulanmadi: Evet" görüyordu).
 */
import { detailRows } from "@/utils/aiDetail";

it("KRİTİK: landmark yanıtının geçmiş satırlarında ham (alt çizgili) anahtar kalmaz; örtü satırı Türkçe", () => {
  const rows = detailRows({ fgs_total: 2, detected: true, nokta_gorunurlugu_dogrulanmadi: true, hw_status: "idle" });
  expect(rows.length).toBeGreaterThan(0); // ARA DOĞRULAMA
  expect(rows.filter((r) => r.label.includes("_"))).toEqual([]);
  const ortu = rows.find((r) => /görünürlü/i.test(r.label));
  expect(ortu).toBeDefined();
});
