// Author: mertaygn, cglrgrkn
/**
 * "Ort. Sıcaklık" KPI'ı — ÖLÇÜM YAPMAYAN bobinlerle SEYRELTİLMEMELİ.
 *
 * DENETİM BULGUSU (2026-08-17). `KpiDashboardScreen` ortalamayı `connectedCoils.length`'e bölüyordu:
 *
 *     avgTemp = connectedCoils.reduce((s, c) => s + c.objectTemp, 0) / connectedCoils.length
 *
 * Ama STM bobinlerinde (1-5) SICAKLIK TELEMETRİSİ YOKTUR: seri protokol yalnız duty/phase/freq/
 * duration döndürür, `objectTemp` daima `0.0` gelir ve backend bunu BİLEREK `0.0` bırakır
 * (`api_server` notu: *"0.0-yerine-NULL yolu BILEREK secilmedi; asagi-akis (PDF/KPI/grafik) 0.0
 * bekliyor"*). Sonuç ölçüldü:
 *
 *     5 STM (ölçüm yok, 0 °C) + 3 ESP @ 50 °C  →  kart **18,8 °C** gösteriyor
 *     yalnız-STM kabin                          →  kart **0,0 °C** ("serin" diye okunur)
 *
 * Üç bobin yanık eşiğine (48 °C) dayanmışken kart 18,8 °C diyor.
 *
 * ⚠️ BU, TESTLE KİLİTLİ BİR DÜRÜSTLÜK DEĞİŞMEZİNİN İHLALİ: 2026-08-09 Tier-2 sahip kararı
 * `CoilParameterPanel` + `CoilThermalHonesty.test.tsx` ile kilitli ve tersini emrediyor —
 * *"'ÖLÇÜLMÜYOR' İLE 'SERİN' AYIRT EDİLEBİLMELİ … ölçüm yokken SAHTE bir sıcaklık değeri
 * gösterilmez; 0 °C 'serin' diye okunur."* Karar SONRA geldi ve bu ekrana taşınmadı
 * (`git log -S"avgTemp"` → tek commit, ilk içe alma).
 *
 * ⚠️ Gerçek termal koruma ETKİLENMİYOR: interlock bobin BAŞINA çalışır (`CoilParameterPanel`),
 * 50 °C'lik ESP bobini `>48` eşiğini geçer ve durdurma komutu gider. Bu bir **yanıltıcı klinik
 * gösterim** bulgusudur, hasta güvenliği değil.
 */
import { hesaplaOrtSicaklik } from "@/screens/KpiDashboardScreen";

type Bobin = { id: number; connected: boolean; running: boolean; objectTemp: number };

const b = (id: number, objectTemp: number, connected = true): Bobin => ({
  id,
  connected,
  running: true,
  objectTemp,
});

// Bobin 1-5 = STM (ölçüm YOK → daima 0), 6-8 = ESP (gerçek ölçüm).
const STM_OLCUMSUZ = [b(1, 0), b(2, 0), b(3, 0), b(4, 0), b(5, 0)];

it("KRİTİK: ölçüm yapmayan bobinler ortalamayı SEYRELTMEZ", () => {
  const sonuc = hesaplaOrtSicaklik([...STM_OLCUMSUZ, b(6, 50), b(7, 50), b(8, 50)]);
  expect(sonuc.deger).toBeCloseTo(50, 1);
});

it("KRİTİK: hiç ölçüm yoksa SAYI GÖSTERİLMEZ ('0 °C serin diye okunur')", () => {
  const sonuc = hesaplaOrtSicaklik(STM_OLCUMSUZ);
  expect(sonuc.olcumVar).toBe(false);
});

it("KRİTİK: kaç bobinin ölçüldüğü bildirilir (şeffaflık)", () => {
  const sonuc = hesaplaOrtSicaklik([...STM_OLCUMSUZ, b(6, 40), b(7, 50)]);
  expect(sonuc.olcumVar).toBe(true);
  expect(sonuc.olcenSayisi).toBe(2);
  expect(sonuc.deger).toBeCloseTo(45, 1);
});

it("karşı-kanıt: TEK bobin ölçüyorsa onun değeri aynen gösterilir", () => {
  const sonuc = hesaplaOrtSicaklik([...STM_OLCUMSUZ, b(6, 47.5)]);
  expect(sonuc.olcumVar).toBe(true);
  expect(sonuc.deger).toBeCloseTo(47.5, 2);
});

it("karşı-kanıt: BAĞLI OLMAYAN bobin hesaba katılmaz", () => {
  const sonuc = hesaplaOrtSicaklik([b(6, 50), b(7, 10, false)]);
  expect(sonuc.olcenSayisi).toBe(1);
  expect(sonuc.deger).toBeCloseTo(50, 1);
});

it("karşı-kanıt: boş liste çökmez", () => {
  expect(hesaplaOrtSicaklik([]).olcumVar).toBe(false);
});

it("karşı-kanıt: NEGATİF/saçma sensör değeri 'ölçüm var' sayılmaz", () => {
  // Sensör arızasında 0 dışında saçma değerler de gelebilir; 0 nöbetçisi tek ayrım noktası
  // olduğu için sıfır-olmayan her değer ölçüm sayılır — ama negatif fiziksel olarak anlamsızdır.
  const sonuc = hesaplaOrtSicaklik([...STM_OLCUMSUZ, b(6, -5)]);
  expect(sonuc.olcumVar).toBe(false);
});
