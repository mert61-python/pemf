// Author: mertaygn, cglrgrkn
/**
 * T3 · Y192 — canlı analiz hızı: `canliSonrakiBekleme(gecenMs, aralikMs)` hedef aralığı uygular; aralık jeton kare tavanı yüzünden
 * 1 sn'nin ALTINA inmez (S-SGI.2: dakikada en çok 60 kare dakika fiyatında), en kısa bekleme 250 ms; aralık verilmezse eski davranış.
 */
import { CANLI_ASGARI_ARALIK_MS, CANLI_ASGARI_BEKLEME_MS, canliSonrakiBekleme } from "@/utils/canliKare";

it("KRİTİK: hedef aralık uygulanır (1 kare / 5 sn)", () => {
  expect(canliSonrakiBekleme(0, 5000)).toBe(5000);
  expect(canliSonrakiBekleme(3000, 5000)).toBe(2000);
  expect(canliSonrakiBekleme(6000, 5000)).toBe(CANLI_ASGARI_BEKLEME_MS);
});

it("KRİTİK: aralık 1 sn'nin altına İNMEZ (jeton kare tavanı); verilmezse eski davranış", () => {
  expect(canliSonrakiBekleme(0, 200)).toBe(CANLI_ASGARI_ARALIK_MS);
  expect(canliSonrakiBekleme(300)).toBe(CANLI_ASGARI_ARALIK_MS - 300);
});
