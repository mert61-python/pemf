// Author: mertaygn
/**
 * GÖRÜNMEYEN BOBİN DURDURULAMAZ — 2026-09-11 saha arızasının kapısı.
 *
 * Kontrol ekranı bobinleri `id <= 7` ile süzüyordu. ESP ağa bağlanınca slot 8 canlı
 * durumda `running` olabiliyordu; "Durdur" onu hedefliyor (çalışan bobinler kümesi),
 * ACK gelmeyince "Durdurma onaylanamadı — bobinler HÂLÂ ÇALIŞIYOR olabilir" uyarısı
 * çıkıyor, ama operatörün o bobine dokunacak hiçbir kontrolü olmuyordu.
 *
 * Kural iki şeyi BİRDEN korumak zorunda:
 *   · cihaz yokken hayalet "Offline" kart GÖSTERME (eski, hâlâ geçerli sahip kararı)
 *   · ortaya çıkan / enerjili olan bobini MUTLAKA göster (yeni arıza)
 */
import { gorunurBobinler, espSlotuGorunur, STM_BOBIN_SAYISI } from "@/services/bobinGorunurlugu";

const b = (id: number, ek: { connected?: boolean; running?: boolean } = {}) => ({
  id,
  connected: false,
  running: false,
  ...ek,
});

/** 7 STM bobini + slot 8 — canlı durumun gerçek şekli (`range(8)`). */
const sekiz = (slot8: { connected?: boolean; running?: boolean } = {}) => [
  ...Array.from({ length: 7 }, (_, i) => b(i + 1)),
  b(8, slot8),
];

test("STM bobinleri (1-7) cevrimdisiyken bile DAIMA cizilir", () => {
  // Fiziksel olarak oradalar: "Offline" göstermek doğru, gizlemek arızayı saklar.
  const g = gorunurBobinler(sekiz());
  expect(g.map((c) => c.id)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  expect(STM_BOBIN_SAYISI).toBe(7);
});

test("ESP YOKKEN slot 8 CIZILMEZ (hayalet bobin sunulmaz)", () => {
  // MUTASYON: süzgeci `() => true` yap → KIRMIZI.
  expect(gorunurBobinler(sekiz()).some((c) => c.id === 8)).toBe(false);
  expect(espSlotuGorunur(sekiz())).toBe(false);
});

test("ESP BAGLANINCA slot 8 cizilir (baslatilip durdurulabilsin)", () => {
  expect(gorunurBobinler(sekiz({ connected: true })).map((c) => c.id)).toContain(8);
  expect(espSlotuGorunur(sekiz({ connected: true }))).toBe(true);
});

test("KRITIK: baglanti DUSSE BILE calisan slot 8 cizilmeye DEVAM eder", () => {
  // ⚠️ ASIL KAPI. Saha arızası tam olarak buydu: bobin enerjili, kart "bağlı değil",
  // ekranda hiçbir kontrol yok, "Durdurma onaylanamadı" uyarısı çıkıyor.
  //
  // MUTASYON: `|| Boolean(c.running)` kısmını sil → KIRMIZI.
  const g = gorunurBobinler(sekiz({ connected: false, running: true }));
  expect(g.map((c) => c.id)).toContain(8);
});

test("slot 8 hem kopuk hem durmussa yine GIZLENIR", () => {
  // Karşıt kanıt: kural "her zaman göster"e kaymasın.
  expect(gorunurBobinler(sekiz({ connected: false, running: false })).some((c) => c.id === 8)).toBe(false);
});

test("alanlar TANIMSIZ gelse bile cokmez ve slot 8 gizli kalir", () => {
  // Canlı durum eksik alanla gelebilir (eski backend / kısmi snapshot).
  const liste = [{ id: 7 }, { id: 8 }];
  expect(gorunurBobinler(liste).map((c) => c.id)).toEqual([7]);
});

test("sira KORUNUR — bobin kartlari yer degistirmez", () => {
  // Süzgeç sıralamayı değiştirirse kartlar her snapshot'ta zıplar; operatör
  // yanlış bobine dokunur.
  const g = gorunurBobinler(sekiz({ connected: true }));
  expect(g.map((c) => c.id)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
});
