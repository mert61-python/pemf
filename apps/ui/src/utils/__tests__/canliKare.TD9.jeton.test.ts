// Author: mertaygn, cglrgrkn
/**
 * TD9 (Y148) — canlı kip jetonu DAKİKA BAŞINA: istemci tarafı oturum kimliği + sayaç (backend kuralının aynası).
 * Backend kuralı ve gerçek tüketim: tests/test_TD9_canli_kip_jetonu_DAKIKA_basina_Y148.py.
 * ⚠️ MUTASYON: kova hesabı kare sayısına dönerse ya da "bulunamadı" / ret kareleri sayılırsa KIRMIZI.
 */
import { CANLI_OTURUM_BASLIGI, canliJetonMetni, canliOturumBaslat } from "@/utils/canliKare";

const SONUC = { tur: "sonuc" as const, metin: "Son kare analiz edildi." };
const BULUNAMADI = { tur: "bulunamadi" as const, metin: "Son kare: kedi bulunamadı" };
const RED = { tur: "red" as const, metin: "Son kare analiz edilemedi: 422" };

it("KRİTİK: 10 dk, saniyede 1 sonuçlu kare → 10 jeton (kare başına DEĞİL)", () => {
  const o = canliOturumBaslat();
  for (let s = 0; s < 600; s++) o.kareBildir(SONUC, 1_000_000 + s * 1000);
  expect(o.jetonSayisi()).toBe(10);
});

it("KRİTİK: yalnız 'bulunamadı' / ret kareleri olan dakika SAYILMAZ", () => {
  const o = canliOturumBaslat();
  for (let s = 0; s < 60; s++) o.kareBildir(s % 2 ? BULUNAMADI : RED, s * 1000); // dakika 0: sonuç yok
  o.kareBildir(SONUC, 61_000); // dakika 1
  expect(o.jetonSayisi()).toBe(1);
});

it("oturum kimliği backend kalıbına uyar ve her oturumda farklı; başlık adı sabit", () => {
  const a = canliOturumBaslat().kimlik;
  const b = canliOturumBaslat().kimlik;
  expect(a).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
  expect(a).not.toBe(b);
  expect(CANLI_OTURUM_BASLIGI).toBe("X-PEMF-Canli-Oturum");
  expect(canliJetonMetni(3)).toContain("3 jeton");
});
