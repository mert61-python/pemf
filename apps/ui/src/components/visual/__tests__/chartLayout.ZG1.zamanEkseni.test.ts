// Author: mertaygn, cglrgrkn
/**
 * ZG-1 (sahip 13 Kasım 2026: "grafikte yakınlaştırma özelliği ve alta zaman ekseni eklenmeli, anlık saat olarak 15:27:13 gibi") —
 * saf yardımcılar: yerel saat metni, okunur adımlı zaman işaretleri, pencere (tümü / son N sn / sabit) → görünür aralık.
 */
import { gorunurAralik, saatMetni, zamanIsaretleri } from "../chartLayout";

const yerel = (s: number, d: number, sn: number) => new Date(2026, 10, 13, s, d, sn).getTime() / 1000;

it("KRİTİK ZG-1: saat metni yerel saat SS:DD:ss (15:27:13)", () => {
  expect(saatMetni(yerel(15, 27, 13))).toBe("15:27:13");
  expect(saatMetni(yerel(9, 5, 3))).toBe("09:05:03");
});

it("KRİTİK ZG-1: işaretler okunur adımda, tam katlarda, etiketler arası ≥ 80 px", () => {
  const bas = yerel(15, 26, 33), son = yerel(15, 27, 3); // 30 sn, 480 px → en çok 6 etiket → 5 sn adım
  const is = zamanIsaretleri(bas, son, 480);
  expect(is.map((x) => x.metin)).toEqual(["15:26:35", "15:26:40", "15:26:45", "15:26:50", "15:26:55", "15:27:00"]);
  const uzun = zamanIsaretleri(yerel(15, 0, 0), yerel(15, 30, 0), 480); // 30 dk → 5 dk adım
  expect(uzun.map((x) => x.metin)).toEqual(["15:00:00", "15:05:00", "15:10:00", "15:15:00", "15:20:00", "15:25:00", "15:30:00"].slice(0, uzun.length));
  expect(uzun.length).toBeLessThanOrEqual(7);
  expect(zamanIsaretleri(10, 10, 480)).toEqual([]);
  expect(zamanIsaretleri(10, 20, 0)).toEqual([]);
});

it("KRİTİK ZG-1: pencere → görünür aralık (tümü / son N sn canlıyı izler / sabit / geçersiz)", () => {
  expect(gorunurAralik(100, 400)).toEqual({ bas: 100, son: 400 });
  expect(gorunurAralik(100, 400, { tip: "tumu" })).toEqual({ bas: 100, son: 400 });
  expect(gorunurAralik(100, 400, { tip: "son", sn: 30 })).toEqual({ bas: 370, son: 400 });
  expect(gorunurAralik(100, 400, { tip: "son", sn: 600 })).toEqual({ bas: 100, son: 400 }); // veri pencereden kısa → tümü
  expect(gorunurAralik(100, 400, { tip: "sabit", bas: 150, son: 160 })).toEqual({ bas: 150, son: 160 });
  expect(gorunurAralik(100, 400, { tip: "sabit", bas: 160, son: 150 })).toEqual({ bas: 100, son: 400 });
  expect(gorunurAralik(Infinity, -Infinity, { tip: "son", sn: 30 })).toBeNull();
});
