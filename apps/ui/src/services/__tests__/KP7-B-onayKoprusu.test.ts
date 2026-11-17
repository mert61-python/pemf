/**
 * KP-7 B (madde 7 · satır / işlev ölçüsü): uygulama içi onay köprüsü (YH-A4) — kayıtlı pencere işleyicisi yoksa ya da EŞZAMANLI
 * patlarsa `null` döner → çağıran ESKİ yerli pencereye düşer; onay sorusu hiçbir durumda sessizce "evet" sayılmaz. İşleyici çalışırsa
 * kullanıcının yanıtının sözü AYNEN döner.
 */
import { setOnayIsleyici, uygulamaIciOnay, type OnayIstegi } from "@/services/onayKoprusu";

const ISTEK: OnayIstegi = { baslik: "Kaydı sil", govde: "Bu kayıt silinsin mi?", tur: "onay" };

afterEach(() => setOnayIsleyici(null));

test("işleyici yokken null; işleyici eşzamanlı patlarsa null (yerli pencereye düşülür); çalışırsa yanıtın sözü döner", async () => {
  expect(uygulamaIciOnay(ISTEK)).toBeNull();
  setOnayIsleyici(() => {
    throw new Error("pencere çizilemedi");
  });
  expect(uygulamaIciOnay(ISTEK)).toBeNull();
  const isleyici = jest.fn(async () => false);
  setOnayIsleyici(isleyici);
  await expect(uygulamaIciOnay(ISTEK)).resolves.toBe(false);
  expect(isleyici).toHaveBeenCalledWith(ISTEK);
});
