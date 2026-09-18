// Author: mertaygn
/**
 * SAHNE SAYFALARI — girdi kaybolması + zarif düşüş.  [AI Hub planı, ADIM 4 / G1, G3, G5]
 * =====================================================================================
 * ÖLÇÜLEN ARIZA (2026-09-09 sahip bildirimi): `AiHubScreen.tsx`'te BEŞ yerde birebir aynı satır
 *   `source={{ uri: result?.image_base64 ? 'data:…' : imageUri }}`
 * sonuç gelir gelmez kullanıcının kendi fotoğrafını ekrandan siliyordu ve bir daha erişilemiyordu.
 * ⚠️ Fantom/petri'de sunucu `image_base64`'ü `no_detection` yolunda da gönderdiği için ternary
 * GİRDİ dalına **asla** düşmüyordu.
 *
 * Bu dosya davranış ölçer: fonksiyonun NE DÖNDÜRDÜĞÜ sınanır, "fonksiyon var mı" değil.
 */
import {
  BIRLESIK_ANAHTARI,
  GIRDI_ANAHTARI,
  sahneSayfalari,
  varsayilanSayfa,
  VARSAYILAN_SAYFA_SIRASI,
} from "@/utils/gorselSahneSayfalari";

const YEREL = "file:///depo/foto.jpg";

function panel(k: string, ad: string, w?: number, h?: number) {
  return { k, ad, image_base64: `B64_${k}`, image_w: w, image_h: h };
}

const YEDI_PANEL = [
  panel("01_input", "Girdi"),
  panel("02_phantom_detect", "Tespit", 800, 600),
  panel("03_phantom_mask", "Maske", 320, 240),
  panel("04_tumors", "Tümörler", 1024, 768),
  panel("05_local_coords", "Koordinat", 500, 900),
  panel("06_predictions", "Tahmin", 1200, 400),
  panel("07_combined", "Birleşik", 1600, 1067),
];

// ============================================================================
// 1. ⚠️ ASIL KAPI — GİRDİ ERİŞİLEBİLİR KALIR
// ============================================================================

test("KRITIK: Girdi sayfasi SUNUCUNUN BILDIRDIGI BOYUTU korur", () => {
  // ⚠️ Uri yerel dosyayla değiştirilir ama BOYUT sunucudan kalmalı: sunucunun `01_input`
  // kopyası AYNI fotoğraftır (yalnız yeniden kodlanmış), dolayısıyla ORANI birebir aynıdır.
  // Boyut düşürülseydi Girdi sayfası yön varsayılanına (4:3) düşerdi ve DİKEY bir telefon
  // fotoğrafı kutunun ~%44'ünü boş bırakırdı — üstelik bu, "girdi kayboluyor" şikâyeti için
  // açtığımız sayfanın ta kendisi.
  //
  // MUTASYON: `image_w: p.image_w, image_h: p.image_h` satırlarını sil → KIRMIZI.
  const dikey = [
    { k: "01_input", ad: "Girdi", image_base64: "B64", image_w: 3024, image_h: 4032 },
    panel("07_combined", "Birleşik", 1600, 1067),
  ];
  const sayfalar = sahneSayfalari({ paneller: dikey }, YEREL);
  const girdi = sayfalar.find((s) => s.k === GIRDI_ANAHTARI);
  expect(girdi?.uri).toBe(YEREL);
  expect(girdi?.image_w).toBe(3024);
  expect(girdi?.image_h).toBe(4032);
});

test("KRITIK: Girdi sayfasi YEREL dosyayi gosterir, sunucunun kopyasini DEGIL", () => {
  // ⚠️ Sunucunun `01_input` paneli yeniden kodlanmış (kapak 1600 px + q85) bir KOPYADIR.
  // Kullanıcının gördüğü "Girdi" kendi çektiği kare olmalı — hem gerçek orijinal budur hem de
  // çip satırında iki ayrı "Girdi" belirmez.
  //
  // MUTASYON: `01_input` dalını kaldır (paneli olduğu gibi geçir) → KIRMIZI.
  const sayfalar = sahneSayfalari({ paneller: YEDI_PANEL }, YEREL);
  const girdi = sayfalar.find((s) => s.k === GIRDI_ANAHTARI);
  expect(girdi?.uri).toBe(YEREL);
  expect(girdi?.uri).not.toContain("base64");
});

test("KRITIK: sonuc gelse de girdi sayfasi KAYBOLMAZ (asil sikayet)", () => {
  // MUTASYON: `sahneSayfalari`yı eski ternary'ye çevir (`sonuc varsa yalnız sonuç`) → KIRMIZI.
  const sayfalar = sahneSayfalari({ paneller: YEDI_PANEL, image_base64: "B64_kok" }, YEREL);
  expect(sayfalar.map((s) => s.k)).toContain(GIRDI_ANAHTARI);
  expect(sayfalar).toHaveLength(7);
});

test("yerel uri yoksa Girdi sayfasi UYDURULMAZ", () => {
  // `undefined` bir uri ile `<Image>` sessizce boş kutu çizerdi.
  const sayfalar = sahneSayfalari({ paneller: YEDI_PANEL }, null);
  expect(sayfalar.map((s) => s.k)).not.toContain(GIRDI_ANAHTARI);
  expect(sayfalar).toHaveLength(6);
});

// ============================================================================
// 2. ⚠️ ZARİF DÜŞÜŞ (G5) — ESKİ BACKEND / PANELSİZ MODÜL
// ============================================================================

test("KRITIK: backend panel gondermezse IKI sayfa uretilir (Girdi + Sonuc)", () => {
  // ⚠️ YENİ İSTEMCİ + ESKİ BACKEND senaryosu: `paneller` alanı hiç yok. Normalizasyon olmasaydı
  // galeri BOŞ kalırdı — kullanıcı sonucunu göremezdi.
  //
  // MUTASYON: panelsiz dalı kaldır → KIRMIZI (boş galeri).
  const sayfalar = sahneSayfalari({ image_base64: "B64_sonuc", image_w: 640, image_h: 480 }, YEREL);
  expect(sayfalar.map((s) => s.k)).toEqual([GIRDI_ANAHTARI, BIRLESIK_ANAHTARI]);
  expect(sayfalar[0].uri).toBe(YEREL);
  expect(sayfalar[1].uri).toBe("data:image/jpeg;base64,B64_sonuc");
  expect(sayfalar[1].image_w).toBe(640);
});

test("KRITIK: BOS image_base64 tasiyan panel ATLANIR (uri 'base64,undefined' olmaz)", () => {
  // ⚠️ Atlanmazsa `source.uri` = "data:image/jpeg;base64,undefined" olur ve `<Image>` hiçbir şey
  // söylemeden boş bir kutu çizer — kullanıcı panelin var olduğunu sanıp boşluğa bakar.
  //
  // MUTASYON: `if (!p.image_base64) continue` satırını sil → KIRMIZI.
  const sayfalar = sahneSayfalari(
    { paneller: [panel("01_input", "Girdi"), { k: "02_phantom_detect", ad: "Tespit" }, panel("07_combined", "Birleşik")] },
    YEREL,
  );
  expect(sayfalar.map((s) => s.k)).toEqual([GIRDI_ANAHTARI, BIRLESIK_ANAHTARI]);
  expect(sayfalar.every((s) => !s.uri.includes("undefined"))).toBe(true);
});

test("hicbir gorsel yoksa BOS dizi doner (cokmez)", () => {
  expect(sahneSayfalari(null, null)).toEqual([]);
  expect(sahneSayfalari({}, null)).toEqual([]);
  expect(sahneSayfalari({ paneller: [] }, null)).toEqual([]);
});

// ============================================================================
// 3. ⚠️ VARSAYILAN SAYFA (G3) — "BİRİNCİL SONUÇ"
// ============================================================================

test("KRITIK: varsayilan sayfa GIRDI DEGIL", () => {
  // Kullanıcı analiz sonucunu görmek için bastı; onu girdi sayfasında karşılamak
  // "analiz çalışmadı" izlenimi verir.
  //
  // MUTASYON: `varsayilanSayfa`yı `() => 0` yap → KIRMIZI.
  const sayfalar = sahneSayfalari({ paneller: YEDI_PANEL }, YEREL);
  expect(sayfalar[varsayilanSayfa(sayfalar)].k).not.toBe(GIRDI_ANAHTARI);
});

test("KRITIK: varsayilan sayfa OKUNMAZ MOZAIK degil, Tahmin paneli", () => {
  // ⚠️ BİLİNÇLİ KARAR (plan §8): mozaik yapısı gereği okunmazdır (6 panel tek karede).
  // Onu varsayılan yapmak, düzeltilmeye çalışılan şikâyetin ilk bakışta AYNEN sürmesi demekti.
  //
  // MUTASYON: `VARSAYILAN_SAYFA_SIRASI`yı `["07_combined"]` yap → KIRMIZI.
  const sayfalar = sahneSayfalari({ paneller: YEDI_PANEL }, YEREL);
  expect(sayfalar[varsayilanSayfa(sayfalar)].k).toBe("06_predictions");
  expect(VARSAYILAN_SAYFA_SIRASI[0]).toBe("06_predictions");
});

test("tercih edilen panel yoksa GIRDI DISINDAKI ilk sayfaya duser", () => {
  const sayfalar = sahneSayfalari({ paneller: [panel("01_input", "Girdi"), panel("02_yolo_dets", "Tespit")] }, YEREL);
  expect(sayfalar[varsayilanSayfa(sayfalar)].k).toBe("02_yolo_dets");
});

test("panelsiz modulde varsayilan SONUC sayfasidir", () => {
  const sayfalar = sahneSayfalari({ image_base64: "B64" }, YEREL);
  expect(varsayilanSayfa(sayfalar)).toBe(1);
});

test("bos listede varsayilan 0 (cokmez)", () => {
  expect(varsayilanSayfa([])).toBe(0);
});

// ============================================================================
// 4. PETRİ AYRI ANAHTARLAR — backend tablosuyla uyum
// ============================================================================

test("KRITIK: petri anahtarlari (02_yolo_dets/03_yolo_masks) DUSURULMEZ", () => {
  // ⚠️ Petri boru hattı fantomdan FARKLI anahtarlar üretir. İstemci yalnız fantom anahtarlarını
  // tanısaydı petri panelleri sessizce kaybolurdu — bu modül anahtarı YORUMLAMAZ, taşır.
  const petri = [
    panel("01_input", "Girdi"),
    panel("02_yolo_dets", "Tespit", 800, 600),
    panel("03_yolo_masks", "Maske", 320, 240),
    panel("04_classify", "Sınıflama", 400, 400),
    panel("05_local_coords", "Koordinat", 500, 500),
    panel("06_predictions", "Tahmin", 600, 600),
    panel("07_combined", "Birleşik", 1200, 900),
  ];
  const sayfalar = sahneSayfalari({ paneller: petri }, YEREL);
  expect(sayfalar.map((s) => s.k)).toEqual(petri.map((p) => p.k));
  expect(sayfalar.map((s) => s.ad)).toContain("Sınıflama");
});
