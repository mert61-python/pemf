// Author: mertaygn
/**
 * EV SAHİBİ EKLENTİLERİ — "Ana Ekran" kalktı, yerine ne geldi (sahip isteği 2026-09-12).
 * ====================================================================================
 * "evcil hayvan modunda ana ekran tabına gerek yok. onu kaldır ve neler ekleyebileceğimizi
 *  düşün." → "4 öneri) hepsini yap pet owner için."
 *
 * Bu dosya iki SAF hesabı kilitler:
 *   #1 Hasta başına SON ANALİZ  (`utils/sonAnaliz`)
 *   #4 Takip serisi             (`utils/takipSerisi`)
 * (#2 "kaldığın yerden" aynı `sonAnaliz` hesabını kullanır; #3 paylaşım backend tarafında —
 *  `tests/test_ai_analiz_pdf.py`.)
 */
import { aramaNormalize } from "@/utils/aramaNormalize";
import {
  adAnahtari,
  hastaAnahtarlari,
  hastaninSonAnalizi,
  hastayaGoreSonAnaliz,
  kimlikAnahtari,
  sonAnalizOzeti,
} from "@/utils/sonAnaliz";
import { takipSerisiKur } from "@/utils/takipSerisi";

// ============================================================================
// #1 — SON ANALİZ EŞLEMESİ
// ============================================================================

test("KRITIK: hasta basina EN YENI analiz secilir (liste sirasina GUVENMEZ)", () => {
  // ⚠️ `/api/ai/log` bugün id DESC dönüyor; bir gün sıralama değişirse kart sessizce
  // ESKİ analizi gösterirdi ve ev sahibi bayat bir sonuca bakardı.
  //
  // MUTASYON: `dahaYeni` kıyasını kaldırıp ilk görüleni tut → KIRMIZI.
  const harita = hastayaGoreSonAnaliz([
    { id: 1, patient_name: "Mia", created_at: "2026-09-01T10:00:00", result_summary: "eski" },
    { id: 2, patient_name: "Mia", created_at: "2026-09-10T10:00:00", result_summary: "YENI" },
    { id: 3, patient_name: "Mia", created_at: "2026-09-05T10:00:00", result_summary: "orta" },
  ]);
  // ⚠️ Anahtar `adAnahtari` ile üretilir — elle "MIA" yazmak Türkçe kuralını ("mia") ıskalar.
  expect(harita.get(adAnahtari("Mia"))?.result_summary).toBe("YENI");
});

test("KRITIK: TURKCE ad eslemesi I/İ tuzagina DUSMEZ (IKI YONDE DE)", () => {
  // Kapı İKİ YÖNÜ de ölçer: İ→i ve I→ı.
  //
  // MUTASYON: `adAnahtari`yı `.toLowerCase()` yap → KIRMIZI (İ→"i"+U+0307).
  // MUTASYON: `.toLocaleUpperCase("tr")` yap → aşağıdaki TEK KAYNAK kıyası KIRMIZI.
  expect(adAnahtari("İpek")).toBe(adAnahtari("İPEK"));   // İ yönü
  expect(adAnahtari("Işık")).toBe(adAnahtari("IŞIK"));    // I yönü (I→ı)
  expect(adAnahtari("Mia")).toBe(adAnahtari("MİA"));      // "mia"nın Türkçe BÜYÜĞÜ "MİA"dır
  expect(adAnahtari(" Mia ")).toBe(adAnahtari("mia"));    // kırpma
  // ⚠️ KARŞIT KANIT — TÜRKÇE KURALI GERÇEKTEN UYGULANIYOR:
  // "MIA" Türkçe'de "mıa" (noktasız) okunur ve "mia" ile AYNI İSİM DEĞİLDİR. Bu kapı
  // ilk yazımda YANLIŞ beklentiyle ("eşleşmeli") yazılmıştı; kod değil TESTİM hatalıydı.
  // İkisini eşitleyen bir normalizasyon, Türkçe'de iki farklı hastayı birleştirirdi.
  expect(adAnahtari("Mia")).not.toBe(adAnahtari("MIA"));
  // ⚠️ Aksan da DÜZLEŞTİRİLMEZ — "Şirin" ile "Sirin" AYNI hasta değildir.
  expect(adAnahtari("Şirin")).not.toBe(adAnahtari("Sirin"));
  // ⚠️ ASIL KAPI: TEK KAYNAK KULLANILIYOR MU. Yukarıdaki eşitlikler, kendi başına yazılmış
  // BAŞKA bir katlama (ör. `toLocaleUpperCase("tr")`) ile de sağlanır — mutasyonla ölçüldü,
  // o hâlde kapı YEŞİL kalıyordu. Bu yüzden çıktı `aramaNormalize` ile BİREBİR kıyaslanır:
  // dördüncü bir kopya yazılırsa kırmızı olur (bu deponun tekrar eden "kopya kural" sınıfı).
  for (const ad of ["İpek", "IŞIK", " Mia ", "Şirin"]) {
    expect(adAnahtari(ad)).toBe(aramaNormalize(ad.trim()));
  }
  const harita = hastayaGoreSonAnaliz([{ id: 1, patient_name: "İpek", created_at: "2026-09-01T10:00:00" }]);
  expect(harita.get(adAnahtari("İPEK"))).toBeTruthy();
});

test("adsiz kayitlar eslemeye GIRMEZ (cokmez)", () => {
  const harita = hastayaGoreSonAnaliz([
    { id: 1, patient_name: "", created_at: "2026-09-01T10:00:00" },
    { id: 2, patient_name: null, created_at: "2026-09-01T10:00:00" },
  ]);
  expect(harita.size).toBe(0);
  expect(hastayaGoreSonAnaliz(null).size).toBe(0);
});

test("ozet TARIH + SONUC tasir, ozet yoksa MODUL adina duser", () => {
  expect(sonAnalizOzeti({ created_at: "2026-09-10T10:00:00", result_summary: "Kapanma %42" }))
    .toContain("Kapanma %42");
  expect(sonAnalizOzeti({ created_at: "2026-09-10T10:00:00", module_label: "Yara Kapanma" }))
    .toContain("Yara Kapanma");
  expect(sonAnalizOzeti(null)).toBeNull();
  expect(sonAnalizOzeti({})).toBeNull();
});

// ============================================================================
// #4 — TAKİP SERİSİ
// ============================================================================

const S = (id: number, gun: string, kapanma: number) => ({
  id,
  patient_name: "Mia",
  module_id: "cell_scratch",
  created_at: `2026-09-${gun}T10:00:00`,
  result_detail: { closure_pct: kapanma },
});

test("KRITIK: seri ESKIDEN YENIYE siralanir", () => {
  // ⚠️ Sıralanmazsa grafik zamanı ters okur ve "iyileşiyor" ile "kötüleşiyor" YER DEĞİŞTİRİR.
  //
  // MUTASYON: `noktalar.sort(...)` satırını sil → KIRMIZI.
  const seri = takipSerisiKur([S(3, "20", 70), S(1, "01", 10), S(2, "10", 40)]);
  expect(seri?.noktalar.map((n) => n.deger)).toEqual([10, 40, 70]);
});

test("KRITIK: TEK NOKTA cizilmez (var olmayan bir takip vaat etme)", () => {
  // MUTASYON: `if (noktalar.length < 2) return null;` kontrolünü kaldır → KIRMIZI.
  expect(takipSerisiKur([S(1, "01", 10)])).toBeNull();
  expect(takipSerisiKur([])).toBeNull();
  expect(takipSerisiKur(null)).toBeNull();
});

test("KRITIK: FARKLI MODULLER ayni eksene DIZILMEZ", () => {
  // ⚠️ "Yara kapanma %42" ile "böbrek sınıfı 3"ü tek eksende göstermek bilgi değil GÜRÜLTÜ.
  // Seri en çok kaydı olan modülden kurulur; kalanlar SAYILARAK dışarıda bırakılır.
  //
  // MUTASYON: modül süzgecini kaldır (tüm kayıtları al) → KIRMIZI.
  const seri = takipSerisiKur([
    S(1, "01", 10),
    S(2, "05", 30),
    { id: 3, patient_name: "Mia", module_id: "kidney_ct", created_at: "2026-09-07T10:00:00", confidence: 0.9 },
  ]);
  expect(seri?.moduleId).toBe("cell_scratch");
  expect(seri?.noktalar).toHaveLength(2);
  expect(seri?.disaridaKalan).toBe(1);
});

test("KRITIK: modul-ozel olcut YOKSA GUVENE duser ve YUZDEYE cevirir", () => {
  // ⚠️ Güven 0-1 aralığında saklanır; etiket "%" diyorsa değer de yüzde OLMALI, yoksa
  // grafik "0,87" yazar ve kullanıcı %87 ile 0,87'yi karıştırır.
  const seri = takipSerisiKur([
    { id: 1, patient_name: "Mia", module_id: "kidney_ct", created_at: "2026-09-01T10:00:00", confidence: 0.5 },
    { id: 2, patient_name: "Mia", module_id: "kidney_ct", created_at: "2026-09-05T10:00:00", confidence: 0.87 },
  ]);
  expect(seri?.baslik).toBe("Güven");
  expect(seri?.birim).toBe("%");
  expect(seri?.noktalar.map((n) => n.deger)).toEqual([50, 87]);
});

test("KRITIK: SAYISAL OLMAYAN olcum seriye GIRMEZ", () => {
  // Backend alanı metin/null gönderirse NaN bir çubuk çizilir (görünmez ama ölçeği bozar).
  const seri = takipSerisiKur([
    S(1, "01", 10),
    { ...S(2, "05", 0), result_detail: { closure_pct: "yok" } },
    S(3, "09", 30),
  ]);
  expect(seri?.noktalar.map((n) => n.deger)).toEqual([10, 30]);
});

test("bozuk tarih COKERTMEZ", () => {
  expect(takipSerisiKur([{ id: 1, patient_name: "M", created_at: "abc" }, S(2, "05", 3)])).toBeNull();
  expect(takipSerisiKur([{ id: 1 }, { id: 2 }] as never)).toBeNull();
});

test("result_detail SOZLUK DEGILSE cokmez (heterojen veri)", () => {
  // ⚠️ `result_detail` üretimde `unknown`: liste/metin/null gelebilir.
  const seri = takipSerisiKur([
    { id: 1, patient_name: "M", module_id: "cell_scratch", created_at: "2026-09-01T10:00:00", result_detail: [1, 2] },
    { id: 2, patient_name: "M", module_id: "cell_scratch", created_at: "2026-09-02T10:00:00", result_detail: "metin" },
  ]);
  expect(seri).toBeNull(); // sayısal ölçüm çıkmadı → çizilecek seri yok
});

// ============================================================================
// #1b — HASTA KİMLİĞİ BAĞI (2026-09-12 taşıması)
// ============================================================================
//
// ⚠️ Analizler hastaya YALNIZ ADLA bağlıydı. Aynı adlı iki hayvanda karışıyor, ad
// düzeltilince kopuyor, PII maskelemesi açıkken tümüyle çöküyordu. Artık önce KİMLİK,
// bulunamazsa AD ile eşlenir.

test("KRITIK: AYNI ADLI iki hayvan KIMLIKLE ayrisir", () => {
  // MUTASYON: `hastayaGoreSonAnaliz`ten `koy(kimlikAnahtari(...))` satırını sil → KIRMIZI.
  const harita = hastayaGoreSonAnaliz([
    { id: 1, patient_name: "Mia", patient_uuid: "kedi-A", created_at: "2026-09-01T10:00:00", result_summary: "A" },
    { id: 2, patient_name: "Mia", patient_uuid: "kedi-B", created_at: "2026-09-05T10:00:00", result_summary: "B" },
  ]);
  expect(hastaninSonAnalizi(harita, { id: "kedi-A", name: "Mia" })?.result_summary).toBe("A");
  expect(hastaninSonAnalizi(harita, { id: "kedi-B", name: "Mia" })?.result_summary).toBe("B");
});

test("KRITIK: KIMLIKSIZ eski kayit AD yedegiyle BULUNUR", () => {
  // ⚠️ Taşıma, adı birden çok hastaya çözülen kayıtları BİLEREK kimliksiz bıraktı.
  // Ad yedeği kaldırılırsa o kayıtlar ekrandan SESSİZCE kaybolur.
  //
  // MUTASYON: `hastaAnahtarlari`ndan `adAnahtari(...)`yı çıkar → KIRMIZI.
  const harita = hastayaGoreSonAnaliz([
    { id: 1, patient_name: "Mia", created_at: "2026-09-01T10:00:00", result_summary: "ESKI" },
  ]);
  expect(hastaninSonAnalizi(harita, { id: "kedi-A", name: "Mia" })?.result_summary).toBe("ESKI");
});

test("KRITIK: KIMLIK adin ONUNE gecer", () => {
  // Aynı hastanın hem kimlikli (yeni) hem kimliksiz (eski) kaydı varsa, kimlik eşleşmesi
  // kazanmalı — aksi hâlde ad anahtarı başka bir hayvanın kaydını getirebilir.
  const harita = hastayaGoreSonAnaliz([
    { id: 1, patient_name: "Mia", patient_uuid: "kedi-A", created_at: "2026-09-01T10:00:00", result_summary: "KIMLIKLI" },
    { id: 2, patient_name: "Mia", created_at: "2026-09-09T10:00:00", result_summary: "ADLA" },
  ]);
  expect(hastaninSonAnalizi(harita, { id: "kedi-A", name: "Mia" })?.result_summary).toBe("KIMLIKLI");
});

test("bos kimlik ANAHTAR uretmez (ad yedegine duser)", () => {
  expect(kimlikAnahtari("")).toBe("");
  expect(kimlikAnahtari(null)).toBe("");
  expect(hastaAnahtarlari({ id: "", name: "Mia" })).toEqual([adAnahtari("Mia")]);
  expect(hastaAnahtarlari({ id: "k1", name: "" })).toEqual([kimlikAnahtari("k1")]);
});

test("KRITIK: kimlik anahtari ADLA CARPISMAZ", () => {
  // ⚠️ Ön ek olmasaydı, kimliği "mia" olan bir hasta ile adı "Mia" olan bir hastanın
  // kayıtları AYNI anahtara düşer ve birbirini ezerdi.
  expect(kimlikAnahtari("mia")).not.toBe(adAnahtari("Mia"));
});
