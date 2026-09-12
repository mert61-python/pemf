// Author: mertaygn
/**
 * WEB KÜÇÜLTME BOŞLUĞU — AI Hub planı §ADIM 1'in üçüncü maddesi.
 *
 * ÖLÇÜLEN DURUM (2026-09-12, düzeltme öncesi): native tarafta `shrinkForUpload` her
 * fotoğrafı 1500 px / JPEG %70'e indiriyordu; **web tarafında hiçbir küçültme YOKTU** —
 * 14 dosya-seçici `URL.createObjectURL(file)` ile HAM dosyayı alıyordu.
 *
 * Zarar:
 *  · aynı analiz platforma göre ~8× farklı boyutta yükleniyordu,
 *  · backend (Starlette) multipart part sınırı 1 MB → web'de modern telefon fotoğrafı
 *    "Part exceeded maximum size of 1024KB" ile REDDEDİLİYORDU.
 *
 * ⚠️ BU DOSYA DAVRANIŞ ÖLÇER: gerçek bir Canvas yolu taklit edilir ve fonksiyonun NE
 * DÖNDÜRDÜĞÜ sınanır — "fonksiyon var mı" değil.
 */
import {
  webIcinKucult,
  YUKLEME_AZAMI_KENAR,
  YUKLEME_JPEG_KALITESI,
  KUCULTME_ESIGI_BAYT,
} from "@/services/gorselKucult";

/** Sahte `File` — jsdom yokken de çalışır. */
function sahteDosya(ad: string, bayt: number, tur = "image/jpeg"): File {
  const blob = { size: bayt, type: tur } as Blob;
  return Object.assign(blob, {
    name: ad,
    lastModified: 0,
    webkitRelativePath: "",
  }) as unknown as File;
}

/** Canvas + createImageBitmap taklidi. `ciktiBayt` üretilen JPEG'in boyutu. */
function kanvasKur(opts: { w: number; h: number; ciktiBayt: number; toBlobNull?: boolean }) {
  const cagrilar: { w: number; h: number; kalite?: number } = { w: 0, h: 0 };
  (globalThis as Record<string, unknown>).createImageBitmap = async () => ({
    width: opts.w,
    height: opts.h,
  });
  (globalThis as Record<string, unknown>).document = {
    createElement: () => ({
      set width(v: number) { cagrilar.w = v; },
      get width() { return cagrilar.w; },
      set height(v: number) { cagrilar.h = v; },
      get height() { return cagrilar.h; },
      getContext: () => ({ drawImage: () => {} }),
      toBlob: (cb: (b: Blob | null) => void, _tur: string, kalite: number) => {
        cagrilar.kalite = kalite;
        cb(opts.toBlobNull ? null : ({ size: opts.ciktiBayt, type: "image/jpeg" } as Blob));
      },
    }),
  };
  (globalThis as Record<string, unknown>).File = class {
    size: number;
    type: string;
    name: string;
    constructor(parts: Blob[], ad: string, o: { type: string }) {
      this.size = parts[0]?.size ?? 0;
      this.type = o.type;
      this.name = ad;
    }
  };
  return cagrilar;
}

afterEach(() => {
  delete (globalThis as Record<string, unknown>).createImageBitmap;
  delete (globalThis as Record<string, unknown>).document;
});

// ============================================================================
// 1. ⚠️ ASIL KAPI — büyük görsel GERÇEKTEN küçültülüyor
// ============================================================================

test("KRITIK: buyuk foto 1500 px tavanina indirilir ve KUCULUR", async () => {
  // MUTASYON: `webIcinKucult`u `async (f) => f` yap → KIRMIZI (web boşluğu geri gelir).
  const izler = kanvasKur({ w: 4032, h: 3024, ciktiBayt: 300 * 1024 });
  const sonuc = await webIcinKucult(sahteDosya("foto.jpg", 8 * 1024 * 1024));

  expect(izler.w).toBe(YUKLEME_AZAMI_KENAR);          // uzun kenar tavana indi
  expect(izler.h).toBe(Math.round(3024 * (YUKLEME_AZAMI_KENAR / 4032)));
  expect(izler.kalite).toBe(YUKLEME_JPEG_KALITESI);   // native ile AYNI kalite
  expect(sonuc.size).toBe(300 * 1024);
  expect(sonuc.size).toBeLessThan(1024 * 1024);       // ⚠️ 1 MB multipart sınırının ALTINDA
  expect(sonuc.name).toBe("foto.jpg");
  expect(sonuc.type).toBe("image/jpeg");
});

test("KRITIK: dikey foto da DOGRU eksenden olceklenir", async () => {
  // MUTASYON: `Math.max(width,height)` → `width` yap → KIRMIZI (dikey fotoda tavan aşılır).
  const izler = kanvasKur({ w: 3024, h: 4032, ciktiBayt: 200 * 1024 });
  await webIcinKucult(sahteDosya("dikey.jpg", 9 * 1024 * 1024));
  expect(izler.h).toBe(YUKLEME_AZAMI_KENAR);
  expect(Math.max(izler.w, izler.h)).toBe(YUKLEME_AZAMI_KENAR);
});

// ============================================================================
// 2. GEREKSİZ İŞ YAPILMAZ
// ============================================================================

test("KRITIK: KUCUK dosya yeniden KODLANMAZ (kalite bosuna dusmez)", async () => {
  // MUTASYON: eşik kontrolünü sil → KIRMIZI (her dosya yeniden kodlanır).
  const izler = kanvasKur({ w: 4032, h: 3024, ciktiBayt: 1 });
  const kucuk = sahteDosya("kucuk.jpg", KUCULTME_ESIGI_BAYT - 1);
  const sonuc = await webIcinKucult(kucuk);
  expect(sonuc).toBe(kucuk);        // AYNI nesne → hiç dokunulmadı
  expect(izler.kalite).toBeUndefined();
});

test("KRITIK: zaten tavanin ALTINDAKI goruntu BUYUTULMEZ", async () => {
  // MUTASYON: `Math.min(1, ...)` kısıtını kaldır → KIRMIZI.
  kanvasKur({ w: 800, h: 600, ciktiBayt: 10 });
  const dosya = sahteDosya("zaten-kucuk.jpg", 2 * 1024 * 1024);
  expect(await webIcinKucult(dosya)).toBe(dosya);
});

test("kucultme dosyayi BUYUTTUYSE orijinal korunur", async () => {
  // Az renkli/gürültüsüz görsellerde JPEG yeniden kodlaması büyütebilir.
  kanvasKur({ w: 4032, h: 3024, ciktiBayt: 20 * 1024 * 1024 });
  const dosya = sahteDosya("garip.jpg", 8 * 1024 * 1024);
  expect(await webIcinKucult(dosya)).toBe(dosya);
});

// ============================================================================
// 3. ⚠️ FAIL-OPEN — AKIŞ ASLA KIRILMAZ
// ============================================================================

test("KRITIK: Canvas COKERSE orijinal dosya doner (analiz engellenmez)", async () => {
  // ⚠️ Küçültme bir OPTİMİZASYONDUR, kapı değil. Hata fırlatırsa operatörün analizi
  // sıkıştırma yüzünden engellenirdi.
  // MUTASYON: `catch { return file; }` dalını sil → KIRMIZI (hata dışarı sızar).
  (globalThis as Record<string, unknown>).createImageBitmap = async () => {
    throw new Error("decode edilemedi");
  };
  const dosya = sahteDosya("bozuk.jpg", 5 * 1024 * 1024);
  await expect(webIcinKucult(dosya)).resolves.toBe(dosya);
});

test("toBlob null donerse orijinal korunur", async () => {
  kanvasKur({ w: 4032, h: 3024, ciktiBayt: 0, toBlobNull: true });
  const dosya = sahteDosya("foto.jpg", 5 * 1024 * 1024);
  expect(await webIcinKucult(dosya)).toBe(dosya);
});

test("gorsel OLMAYAN dosyaya dokunulmaz", async () => {
  kanvasKur({ w: 100, h: 100, ciktiBayt: 1 });
  const pdf = sahteDosya("rapor.pdf", 5 * 1024 * 1024, "application/pdf");
  expect(await webIcinKucult(pdf)).toBe(pdf);
});

// ============================================================================
// 4. ⚠️ NATIVE İLE TEK KAYNAK
// ============================================================================

test("KRITIK: sabitler NATIVE shrinkForUpload ile AYNI", () => {
  // ⚠️ Ayrışırsa aynı analiz platforma göre farklı çözünürlükte gider — yani model
  // girdisi platforma bağımlı olur. Bu, düzeltilmeye çalışılan arızanın ta kendisidir.
  //
  // MUTASYON: `YUKLEME_AZAMI_KENAR`ı 1000 yap → KIRMIZI.
  /* eslint-disable @typescript-eslint/no-require-imports */
  const fs = require("fs");
  const path = require("path");
  /* eslint-enable @typescript-eslint/no-require-imports */
  const src = fs.readFileSync(
    path.join(__dirname, "..", "..", "screens", "AiHubScreen.tsx"),
    "utf8",
  ) as string;

  expect(src).toContain(`resize: { width: ${YUKLEME_AZAMI_KENAR} }`);
  expect(src).toContain(`compress: ${YUKLEME_JPEG_KALITESI}`);
});

test("KRITIK: TUM web secicileri kucultmeden GECIYOR", () => {
  // ⚠️ 14 seçici var; biri atlanırsa o modülde ham dosya yüklenmeye devam eder ve
  // arıza SESSİZCE yaşamaya devam ederdi (yalnız bir modülde).
  //
  // MUTASYON: bir `webIcinKucult(` çağrısını `setImageFile(file)`a geri çevir → KIRMIZI.
  /* eslint-disable @typescript-eslint/no-require-imports */
  const fs = require("fs");
  const path = require("path");
  /* eslint-enable @typescript-eslint/no-require-imports */
  const src = fs.readFileSync(
    path.join(__dirname, "..", "..", "screens", "AiHubScreen.tsx"),
    "utf8",
  ) as string;

  const kucultme = (src.match(/webIcinKucult\(file\)/g) || []).length;
  expect(kucultme).toBe(14);
  // Ham dosyayı doğrudan state'e koyan hiçbir yol KALMAMALI.
  expect(src).not.toContain("setImageFile(file)");
});
