// Author: mertaygn
/**
 * "Bağlı Bobin" / "Çalışan Bobin" KPI'ının PAYDASI — ekranın geri kalanıyla AYNI olmalı.
 *
 * SAHA BULGUSU (2026-09-22, sahip ekran görüntüsüyle bildirdi): Ana Ekran **7 / 7** derken
 * Raporlar ekranı **7 / 8** ve veri yokken **0 / 8** gösteriyordu. Aynı cihaz, iki farklı
 * bobin sayısı.
 *
 * İKİ AYRI KUSUR VARDI, İKİSİ DE PAYDAYI 8 YAPIYORDU:
 *
 *  1) `KpiDashboardScreen` bobinleri `gorunurBobinler` SÜZGECİNDEN GEÇİRMİYORDU — tek
 *     ekran. Dashboard, Control ve SensorMonitor hepsi süzgeci kullanıyor; bu ekran
 *     ham `snapshot.coils`i alıyordu. Backend ESP slotunu (8) takılı olmasa da listede
 *     bildirdiği için `coils.length === 8` oluyordu → "7 / 8".
 *
 *  2) Veri yokken geri düşülen sabit `8`di (`coils.length || 8`). ESP 2026-09-11'de
 *     söküldü ve bobin 6-7 STM'ye taşındı; fiziksel sayı **7**. → "0 / 8".
 *
 * ⚠️ DÜZELTME "8'i 7 YAP" DEĞİLDİR. Sahip kaydı açık: *"ileride tekrar hibrit ESP+STM
 * sistemine dönebilirim"*. Payda TEK KAYNAKTAN türetilir (`bobinGorunurlugu`): ESP slotu
 * ORTAYA ÇIKARSA payda yine 8 olmalıdır. Aşağıdaki karşı-kanıt testleri tam da bunu
 * kilitler — 7'yi sabit yazan bir "düzeltme" onları KIRAR.
 */
import { readFileSync } from "fs";
import { join } from "path";
import { hesaplaBobinSayisi } from "@/screens/KpiDashboardScreen";
import { STM_BOBIN_SAYISI } from "@/services/bobinGorunurlugu";

type Bobin = { id: number; connected: boolean; running: boolean };

const b = (id: number, connected = true, running = false): Bobin => ({ id, connected, running });

/** Sahadaki hâl: STM 1-7 bağlı, ESP slotu (8) backend listesinde AMA takılı değil. */
const STM_YEDI_ARTI_HAYALET_ESP: Bobin[] = [
  b(1), b(2), b(3), b(4), b(5), b(6), b(7), b(8, false, false),
];

it("KRİTİK: takılı OLMAYAN ESP slotu paydaya SAYILMAZ (bildirilen '7 / 8' kusuru)", () => {
  expect(hesaplaBobinSayisi(STM_YEDI_ARTI_HAYALET_ESP)).toBe(7);
});

it("KRİTİK: veri yokken payda STM'nin FİZİKSEL sayısı olur ('0 / 8' kusuru)", () => {
  expect(hesaplaBobinSayisi([])).toBe(STM_BOBIN_SAYISI);
});

it("karşı-kanıt: ESP slotu BAĞLANIRSA payda yine 8 olur (7 SABİT YAZILMAMIŞ)", () => {
  const hibrit = [...STM_YEDI_ARTI_HAYALET_ESP.slice(0, 7), b(8, true, false)];
  expect(hesaplaBobinSayisi(hibrit)).toBe(8);
});

it("karşı-kanıt: ESP slotu bağlı değil ama ÇALIŞIYORSA yine sayılır (enerjili bobin gizlenmez)", () => {
  const enerjili = [...STM_YEDI_ARTI_HAYALET_ESP.slice(0, 7), b(8, false, true)];
  expect(hesaplaBobinSayisi(enerjili)).toBe(8);
});

it("payda ekranın geri kalanıyla AYNI kaynaktan türer (tek kaynak kontrolü)", () => {
  const yalnizStm = STM_YEDI_ARTI_HAYALET_ESP.slice(0, STM_BOBIN_SAYISI);
  expect(hesaplaBobinSayisi(yalnizStm)).toBe(STM_BOBIN_SAYISI);
});

/**
 * ⚠️ KÖR NOKTA KAPATMA: yukarıdaki testler yalnız SAF FONKSİYONU ölçer. Fonksiyon doğruyken
 * ekranın onu ÇAĞIRMAMASI (eski `coils.length || 8` satırının geri gelmesi) hepsini yeşil
 * bırakırdı — bildirilen kusur tam olarak oydu. Bu yüzden ÜRETİM KAYNAĞINA da bakılır.
 *
 * ⚠️ Yorumlar SOYULUR: bu deponun "yorum kapıyı kandırdı" sınıfı — aradığımız dizeler
 * (`|| 8`, `snapshot.coils ?? []`) bu dosyanın ve ekranın AÇIKLAMA yorumlarında da geçiyor.
 */
function kaynakSoyulmus(): string {
  const ham = readFileSync(join(__dirname, "..", "KpiDashboardScreen.tsx"), "utf8");
  return ham.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

it("KRİTİK: EKRAN paydayı gerçekten bu fonksiyondan alıyor (saf test tek başına KÖR)", () => {
  const k = kaynakSoyulmus();
  expect(k).toMatch(/coilCount\s*=\s*hesaplaBobinSayisi\(/);
  expect(k).not.toMatch(/coils\.length\s*\|\|\s*8/);
});

it("KRİTİK: bobin listesi EKRANDA da süzgeçten geçiyor (ham snapshot kullanılmıyor)", () => {
  const k = kaynakSoyulmus();
  expect(k).toMatch(/const\s+coils\s*=\s*gorunurBobinler\(/);
});
