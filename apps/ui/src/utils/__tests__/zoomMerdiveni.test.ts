// Author: mertaygn
/**
 * ZOOM MERDİVENİ — kaynak piksele kilitli yakınlaştırma.  [AI Hub planı, ADIM 4 / G12]
 * ===================================================================================
 * ⚠️ SABİT `[1,2,4]` MERDİVENİ YETMİYOR — ÖLÇÜLDÜ (2026-09-10 demo turu): 700×540'lık launcher
 * penceresinde sahne ~600 px. 6048 px genişliğindeki bir mozaikte %400 bile gömülü metni
 * yalnız 9,2 px'e çıkarır (hâlâ okunmaz); 1:1 kaynak piksel ise pencereden BAĞIMSIZ ~12 px verir.
 *
 * ⚠️ 4096 px: Android OpenGL doku sınırı. Daha büyük kareyi 1:1 çizmek boş/siyah doku üretir —
 * var olmayan bir yetenek vaat etmemek için o basamak GİZLENİR.
 */
import {
  birebirOrani,
  basamakEtiketi,
  DOKU_SINIRI_PX,
  oncekiBasamak,
  sonrakiBasamak,
  zoomBasamaklari,
  zoomSinirla,
} from "@/utils/zoomMerdiveni";

// ============================================================================
// 1. ⚠️ ASIL KAPI — SON BASAMAK 1:1 KAYNAK PİKSEL
// ============================================================================

test("KRITIK: buyuk karede son basamak 1:1 KAYNAK PIKSEL (sabit 4x degil)", () => {
  // 3000 px kaynak, 600 px kutu → 1:1 = 5,0. Sabit merdiven burada 4'te kalırdı.
  //
  // MUTASYON: `zoomBasamaklari`yı `() => [1,2,4]` yap → KIRMIZI.
  const b = zoomBasamaklari({ kaynakW: 3000, kaynakH: 2000, kutuW: 600 });
  expect(b[b.length - 1]).toBeCloseTo(5.0, 5);
});

test("KRITIK: hicbir basamak 1:1'i ASMAZ", () => {
  // ⚠️ 1:1'in üstüne çıkmak yalnız JPEG bloklarını büyütür, bilgi EKLEMEZ. Kullanıcı
  // "daha fazla yakınlaştırdım ama netleşmedi" der ve zoom'a güveni biter.
  //
  // MUTASYON: `filter((b) => b < birebir - tol)` satırını kaldır → KIRMIZI (2 > 1,5 kalır).
  const b = zoomBasamaklari({ kaynakW: 900, kaynakH: 600, kutuW: 600 }); // 1:1 = 1,5
  expect(Math.max(...b)).toBeCloseTo(1.5, 5);
  expect(b.some((x) => x > 1.5 + 1e-6)).toBe(false);
});

test("KRITIK: 4096 px USTUNDE 1:1 basamagi GIZLENIR (Android doku siniri)", () => {
  // MUTASYON: `uzunKenar <= DOKU_SINIRI_PX` kontrolünü kaldır → KIRMIZI.
  const b = zoomBasamaklari({ kaynakW: 6048, kaynakH: 12256, kutuW: 600 });
  expect(b).toEqual([1, 2]);
  expect(Math.max(...b)).toBeLessThan(6048 / 600);
  // Sınırın kendisi geçerli olmalı (kapsayıcı):
  const sinirda = zoomBasamaklari({ kaynakW: DOKU_SINIRI_PX, kaynakH: DOKU_SINIRI_PX, kutuW: 512 });
  expect(sinirda[sinirda.length - 1]).toBeCloseTo(8, 5);
});

test("kaynak kutudan KUCUKSE yakinlastiracak sey yok", () => {
  // 400 px kaynak, 600 px kutu → zaten büyütülmüş çiziliyor; merdiven tek basamak.
  expect(zoomBasamaklari({ kaynakW: 400, kaynakH: 300, kutuW: 600 })).toEqual([1]);
});

test("KRITIK: image_w bilinmiyorsa UYDURMA 1:1 basamagi gosterilmez", () => {
  // Eski backend `image_w` göndermiyor; 1:1 hesaplanamaz. Sahte bir basamak göstermek
  // kullanıcıya var olmayan bir çözünürlük vaat ederdi.
  expect(zoomBasamaklari({ kaynakW: null, kaynakH: null, kutuW: 600 })).toEqual([1, 2]);
  expect(zoomBasamaklari({ kutuW: 0 })).toEqual([1, 2]);
});

// ============================================================================
// 2. GEZİNME — SARMA YOK
// ============================================================================

test("KRITIK: basamaklar SINIRDA durur (sarma yok)", () => {
  // MUTASYON: `Math.min(i+1, son)` yerine `(i+1) % n` → KIRMIZI (en yakından en uzağa atlar).
  const b = zoomBasamaklari({ kaynakW: 3000, kaynakH: 2000, kutuW: 600 }); // [1, 2, 5]
  expect(sonrakiBasamak(b, 5)).toBeCloseTo(5, 5);
  expect(oncekiBasamak(b, 1)).toBeCloseTo(1, 5);
  expect(sonrakiBasamak(b, 1)).toBeCloseTo(2, 5);
  expect(oncekiBasamak(b, 5)).toBeCloseTo(2, 5);
});

test("bilinmeyen deger ilk basamaga toparlanir (cokmez)", () => {
  const b = [1, 2];
  expect(sonrakiBasamak(b, 3.7)).toBe(1);
  expect(oncekiBasamak(b, 3.7)).toBe(1);
});

// ============================================================================
// 3. ETİKET — KULLANICI NE GÖRDÜĞÜNÜ BİLSİN
// ============================================================================

test("KRITIK: kaynak-kilitli son basamak '1:1' yazar, '%500' DEGIL", () => {
  // "%500" sayısı kullanıcıya hiçbir şey söylemez; "1:1" ise "artık daha fazlası yok,
  // gerçek piksellere bakıyorsun" der.
  const g = { kaynakW: 3000, kaynakH: 2000, kutuW: 600 };
  const b = zoomBasamaklari(g);
  const birebir = birebirOrani(g);
  expect(basamakEtiketi(b[b.length - 1], birebir)).toBe("1:1");
  expect(basamakEtiketi(1, birebir)).toBe("%100");
  expect(basamakEtiketi(2, birebir)).toBe("%200");
});

test("KRITIK: 1:1 TAM SAYIYA denk gelse de '1:1' yazar", () => {
  // ⚠️ İlk yazımda etiket "son basamak tam sayı değilse 1:1'dir" diye TAHMİN ediyordu;
  // 1200/600 = 2,0 gibi tam sayılı bir 1:1'i "%200" yazıyordu. Etiket artık tahmin değil,
  // `birebirOrani()` hesabı.
  //
  // MUTASYON: `basamakEtiketi`i eski "tam sayı değilse 1:1" sezgisine çevir → KIRMIZI.
  const g = { kaynakW: 1200, kaynakH: 800, kutuW: 600 };
  expect(basamakEtiketi(2, birebirOrani(g))).toBe("1:1");
});

test("1:1 YOKKEN etiket her zaman yuzde", () => {
  expect(basamakEtiketi(2, null)).toBe("%200");
  expect(basamakEtiketi(1, null)).toBe("%100");
});

// ============================================================================
// 4. ⚠️ SÜREKLİ ZOOM SINIRI (fare tekerleği)
// ============================================================================

test("KRITIK: tekerlek 1:1'i ASAMAZ", () => {
  // ⚠️ Tekerlek sürekli değer üretir; merdiven basamaklarına takılı değildir. Sınır olmazsa
  // kullanıcı sonsuza kadar yakınlaştırır ve yalnız JPEG blokları büyür — "yakınlaştırdım ama
  // netleşmedi" hissi.
  //
  // MUTASYON: `Math.min(..., enUst)` sınırını kaldır → KIRMIZI.
  const g = { kaynakW: 1200, kaynakH: 400, kutuW: 600 }; // 1:1 = 2,0
  const b = zoomBasamaklari(g);
  const bir = birebirOrani(g);
  expect(zoomSinirla(99, bir, b)).toBeCloseTo(2, 5);
  expect(zoomSinirla(1.5, bir, b)).toBeCloseTo(1.5, 5);
});

test("KRITIK: tekerlek SIGDIRMANIN altina inemez", () => {
  // ⚠️ 1 = ekrana sığdır. Altına inmek görüntüyü ortada küçültür, kullanıcı "kayboldu" sanır.
  const g = { kaynakW: 1200, kaynakH: 400, kutuW: 600 };
  expect(zoomSinirla(0.2, birebirOrani(g), zoomBasamaklari(g))).toBe(1);
  expect(zoomSinirla(-5, null, [1])).toBe(1);
});

test("1:1 YOKKEN ust sinir merdivenin son basamagidir", () => {
  // Kaynak boyutu bilinmiyorsa (eski backend) merdiven [1,2]; tekerlek 2'yi aşmamalı.
  expect(zoomSinirla(50, null, [1, 2])).toBe(2);
});
