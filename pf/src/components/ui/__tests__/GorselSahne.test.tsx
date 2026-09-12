// Author: mertaygn
/**
 * GÖRSEL SAHNE — oran kilidi · gezinme · yükseklik bütçesi · tam ekran.
 * [AI Hub planı, ADIM 4 / G2, G3, G4, G6, G10, G11]
 * =====================================================================
 * ⚠️ BU DOSYA `onLayout` ATEŞLER. Plan turunda ölçüldü: bugüne dek HİÇBİR test `onLayout`
 * tetiklemiyordu, dolayısıyla oran-kilidi dalı hiç koşmuyor ve ilgili kapılar SAHTE-YEŞİL
 * kalıyordu. Genişliği testin KENDİSİ verir.
 *
 * ⚠️ ÖLÇÜLEN ARIZA (2026-09-10 demo turu): sahneye tam `useStageHeight()` verilince 700×540'lık
 * launcher penceresinde içerik taştı ve oklar kırpıldı. Kutu yüksekliğini TEK BAŞINA ölçen bir
 * kapı bu taşmayı YEŞİL geçer — bu yüzden toplam yükseklik ayrı ölçülür (G11).
 */
import { fireEvent, render } from "@testing-library/react-native";
import { GorselSahne, KONTROL_TAHMINI } from "@/components/ui/GorselSahne";
import type { SahneSayfasi } from "@/utils/gorselSahneSayfalari";
import { Text, View } from "react-native";

const KAP_W = 900;

function sayfa(k: string, ad: string, w?: number, h?: number): SahneSayfasi {
  return { k, ad, uri: `data:image/jpeg;base64,B64_${k}`, image_w: w, image_h: h };
}

const YEDI: SahneSayfasi[] = [
  { k: "01_input", ad: "Girdi", uri: "file:///depo/foto.jpg" },
  sayfa("02_phantom_detect", "Tespit", 800, 600),
  sayfa("03_phantom_mask", "Maske", 320, 240),
  sayfa("04_tumors", "Tümörler", 1024, 768),
  sayfa("05_local_coords", "Koordinat", 500, 900),
  sayfa("06_predictions", "Tahmin", 1200, 400),
  sayfa("07_combined", "Birleşik", 1600, 1067),
];

/** Kabın genişliğini ve kontrol satırının yüksekliğini testin KENDİSİ verir. */
function olc(api: ReturnType<typeof render>, kontrolY = KONTROL_TAHMINI, testID = "gorsel-sahne") {
  const kap = api.getByTestId(testID).children[0] as never;
  fireEvent(kap, "layout", { nativeEvent: { layout: { width: KAP_W, height: 400 } } });
  fireEvent(api.getByTestId(`${testID}-kontrol`), "layout", {
    nativeEvent: { layout: { width: KAP_W, height: kontrolY } },
  });
}

function kutuOlcusu(api: ReturnType<typeof render>, testID = "gorsel-sahne") {
  const st = api.getByTestId(`${testID}-kutu`).props.style;
  const duz = Array.isArray(st) ? Object.assign({}, ...st.filter(Boolean)) : st;
  return { width: duz.width as number, height: duz.height as number };
}

// ============================================================================
// 1. ⚠️ ORAN KİLİDİ (G2) — LETTERBOX YOK, İŞARET KAYMASI YOK
// ============================================================================

test("KRITIK: kutu orani AKTIF PANELIN oranina uyar", () => {
  // MUTASYON: `kameraKutusu(...)` yerine sabit `{width: kapW, height: tavanY}` → KIRMIZI.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  const k = kutuOlcusu(api);
  // Varsayılan sayfa "Tahmin" (1200×400) → oran 3,0
  expect(k.width / k.height).toBeCloseTo(1200 / 400, 1);
});

test("KRITIK: CIP degisince oran DA degisir (kutu panele gore yeniden hesaplanir)", () => {
  // ⚠️ Oran tek seferlik hesaplansaydı dikey bir panele geçildiğinde görüntü letterbox'lanır
  // ve üzerine çizilen işaretler kayardı.
  //
  // MUTASYON: `oran`ı ilk sayfadan hesapla (indeksi yok say) → KIRMIZI.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  const yatay = kutuOlcusu(api);
  fireEvent.press(api.getByTestId("gorsel-sahne-cip-05_local_coords")); // 500×900 (dikey)
  const dikey = kutuOlcusu(api);
  expect(yatay.width / yatay.height).toBeGreaterThan(1);
  expect(dikey.width / dikey.height).toBeCloseTo(500 / 900, 1);
});

test("boyut BILINMEYEN sayfada kutu yon varsayilanina duser (cokmez)", () => {
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  fireEvent.press(api.getByTestId("gorsel-sahne-cip-01_input")); // image_w yok
  const k = kutuOlcusu(api);
  expect(k.width).toBeGreaterThan(0);
  expect(k.height).toBeGreaterThan(0);
});

// ============================================================================
// 2. ⚠️ YÜKSEKLİK BÜTÇESİ (G4 + G11)
// ============================================================================

test("KRITIK: TOPLAM yukseklik (kutu + kontrol) tavani ASMAZ", () => {
  // ⚠️ G4 yalnız KUTUYU ölçer ve toplam taşarken YEŞİL kalır — demoda bizzat gözlendi:
  // sahneye tam `useStageHeight()` verilince 700×540'ta oklar kırpıldı.
  //
  // MUTASYON: `tavanY - kontrolY` çıkarmasını `tavanY` yap → KIRMIZI.
  const TAVAN = 243; // 700×540 launcher penceresinde ölçülen sahne tavanı
  const KONTROL = 96;
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={TAVAN} />);
  olc(api, KONTROL);
  const k = kutuOlcusu(api);
  expect(k.height + KONTROL).toBeLessThanOrEqual(TAVAN);
});

test("KRITIK: kontrol satiri BUYURSE (cipler sarinca) kutu KUCULUR", () => {
  // Çipler dar ekranda iki satıra sarar; bütçe sabit bir sayı olsaydı içerik yine taşardı.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api, 80);
  const dar = kutuOlcusu(api).height;
  fireEvent(api.getByTestId("gorsel-sahne-kontrol"), "layout", {
    nativeEvent: { layout: { width: KAP_W, height: 160 } },
  });
  expect(kutuOlcusu(api).height).toBeLessThan(dar);
});

test("kutu ASGARI yuksekligin altina inmez", () => {
  // Kontrol satırı tavandan büyükse bile tanınmaz bir şerit çizilmez.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={100} />);
  olc(api, 300);
  expect(kutuOlcusu(api).height).toBeGreaterThanOrEqual(100);
});

// ============================================================================
// 3. ⚠️ GEZİNME (G3) — SARMA YOK, SAYAÇ DOĞRU
// ============================================================================

test("KRITIK: oklar SINIRDA durur (sarma YOK) ve sayac dogru", () => {
  // MUTASYON: `clamp`i `(i + yon + adet) % adet` yap → KIRMIZI.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  expect(api.getByTestId("gorsel-sahne-sayac").props.children.join("")).toContain("Tahmin");

  for (let i = 0; i < 10; i++) fireEvent.press(api.getByTestId("gorsel-sahne-sonraki"));
  expect(api.getByTestId("gorsel-sahne-sayac").props.children.join("")).toContain("7/7");

  for (let i = 0; i < 20; i++) fireEvent.press(api.getByTestId("gorsel-sahne-onceki"));
  expect(api.getByTestId("gorsel-sahne-sayac").props.children.join("")).toContain("1/7");
});

test("KRITIK: sinirlardaki oklar DEVRE DISI (tiklanabilir gorunup hicbir sey yapmaz DEGIL)", () => {
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  for (let i = 0; i < 10; i++) fireEvent.press(api.getByTestId("gorsel-sahne-onceki"));
  expect(api.getByTestId("gorsel-sahne-onceki").props.accessibilityState.disabled).toBe(true);
  expect(api.getByTestId("gorsel-sahne-sonraki").props.accessibilityState.disabled).toBe(false);
});

test("KRITIK: YENI ANALIZDE sayfa indeksi SIFIRLANIR", () => {
  // ⚠️ Sıfırlanmazsa 7 panelli analizden 2 sayfalı sonuca geçince indeks aralık dışında
  // kalır ve ekran boşalır; ayrıca eski sonucun izi yeni analizde görünür.
  //
  // MUTASYON: `imza !== oncekiImza` blogunu sil → KIRMIZI.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} sifirlaAnahtari="analiz-1" />);
  olc(api);
  fireEvent.press(api.getByTestId("gorsel-sahne-cip-07_combined"));
  expect(api.getByTestId("gorsel-sahne-sayac").props.children.join("")).toContain("7/7");

  api.rerender(<GorselSahne sayfalar={YEDI} tavanY={400} sifirlaAnahtari="analiz-2" />);
  expect(api.getByTestId("gorsel-sahne-sayac").props.children.join("")).toContain("6/7");
});

test("KRITIK: sayfa sayisi KUCULUNCE indeks araliga toparlanir (bos ekran YOK)", () => {
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} sifirlaAnahtari="a" />);
  olc(api);
  fireEvent.press(api.getByTestId("gorsel-sahne-cip-07_combined"));
  api.rerender(<GorselSahne sayfalar={YEDI.slice(0, 2)} tavanY={400} sifirlaAnahtari="a" />);
  expect(api.getByTestId("gorsel-sahne-sayac").props.children.join("")).toContain("2/2");
  expect(api.getByTestId("gorsel-sahne-gorsel-sahne")).toBeTruthy();
});

test("sayfa yoksa BOS dugumu cizilir (cokmez)", () => {
  const api = render(<GorselSahne sayfalar={[]} tavanY={400} bos={<Text>Görüntü seçilmedi</Text>} />);
  expect(api.getByText("Görüntü seçilmedi")).toBeTruthy();
  expect(api.queryByTestId("gorsel-sahne-kutu")).toBeNull();
});

// ============================================================================
// 4. ⚠️ İŞARET HİZASI (G10) — TIBBİ KARAR EKRANI
// ============================================================================

test("KRITIK: ust katman taban gorselle AYNI SAYISAL kutuyu alir", () => {
  // ⚠️ Overlay `{%100/%100}` alsaydı ve kap oran-kilitsiz olsaydı organ/tümör işaretleri
  // görüntüyle KAYARDI — yanlış organa bakılmasına yol açar.
  //
  // MUTASYON: `ustKatman?.(kutu)` yerine `ustKatman?.({width:0,height:0})` → KIRMIZI.
  const gorulen: { width: number; height: number }[] = [];
  const api = render(
    <GorselSahne
      sayfalar={YEDI}
      tavanY={400}
      ustKatman={(k) => {
        gorulen.push(k);
        return <View testID="ust-katman" style={{ width: k.width, height: k.height }} />;
      }}
    />,
  );
  olc(api);
  const k = kutuOlcusu(api);
  const son = gorulen[gorulen.length - 1];
  expect(son).toEqual(k);

  const gorselStil = api.getByTestId("gorsel-sahne-gorsel-sahne").props.style;
  expect(gorselStil.width).toBe(k.width);
  expect(gorselStil.height).toBe(k.height);
  // Taban görselin KENDİSİ açık sayısal ölçü taşımalı — yüzde DEĞİL.
  expect(typeof gorselStil.width).toBe("number");
});

// ============================================================================
// 5. ⚠️ TAM EKRAN + ZOOM (G6, G12)
// ============================================================================

test("KRITIK: tam ekran ACILIR, AYNI uri, kapanista SAYFA INDEKSI KORUNUR", () => {
  // ⚠️ Kapanışta indeks sıfırlansaydı operatör 7 panel içinde bulduğu yeri her seferinde
  // kaybederdi.
  //
  // MUTASYON: kapatma düğmesine `setIndeks(0)` ekle → KIRMIZI.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  fireEvent.press(api.getByTestId("gorsel-sahne-cip-04_tumors"));
  fireEvent.press(api.getByTestId("gorsel-sahne-tam-ekran"));

  const tam = api.getByTestId("gorsel-sahne-gorsel-tam");
  expect(tam.props.source.uri).toBe(api.getByTestId("gorsel-sahne-gorsel-sahne").props.source.uri);

  fireEvent.press(api.getByTestId("gorsel-sahne-tam-ekran-kapat"));
  expect(api.getByTestId("gorsel-sahne-sayac").props.children.join("")).toContain("4/7");
});

test("KRITIK: %200'de SAYISAL boyut 2 kat, son basamak 1:1 KAYNAK PIKSEL", () => {
  // 3000×1000 kaynak, 900 px kutu → merdiven [1, 2, 3,33]. İlk basamak %200, son basamak 1:1.
  //
  // ⚠️ Bu testin ilk yazımı varsayılan paneli (1200×400) kullanıyordu; orada 1:1 zaten 1,33
  // olduğu için 2× basamağı HAKLI OLARAK eleniyordu ve test kodu değil KENDİNİ ölçüyordu.
  // Kaynak, 2×'in 1:1'in ALTINDA kaldığı bir boyuta çekildi.
  //
  // MUTASYON: zoom çarpanını görsele uygulama (sabit kutu) → KIRMIZI.
  const buyuk: SahneSayfasi[] = [sayfa("07_combined", "Birleşik", 3000, 1000)];
  const api = render(<GorselSahne sayfalar={buyuk} tavanY={400} />);
  olc(api);
  const k = kutuOlcusu(api);
  fireEvent.press(api.getByTestId("gorsel-sahne-tam-ekran"));

  fireEvent.press(api.getByTestId("gorsel-sahne-yakinlastir"));
  const iki = api.getByTestId("gorsel-sahne-gorsel-tam").props.style;
  expect(iki.width).toBe(Math.round(k.width * 2));
  expect(iki.height).toBe(Math.round(k.height * 2));
  expect(api.getByTestId("gorsel-sahne-zoom-etiket").props.children).toBe("%200");

  // Son basamak: kaynak pikselin TAM kendisi — kutu genişliğinden bağımsız 3000 px.
  fireEvent.press(api.getByTestId("gorsel-sahne-yakinlastir"));
  expect(api.getByTestId("gorsel-sahne-gorsel-tam").props.style.width).toBe(3000);
  expect(api.getByTestId("gorsel-sahne-zoom-etiket").props.children).toBe("1:1");

  // ⚠️ Daha ileri gitmez — 1:1'i aşmak yalnız JPEG bloklarını büyütür.
  fireEvent.press(api.getByTestId("gorsel-sahne-yakinlastir"));
  expect(api.getByTestId("gorsel-sahne-gorsel-tam").props.style.width).toBe(3000);
});

test("KRITIK: DEV mozaikte 1:1 basamagi YOK, zoom %200'de durur (Android doku siniri)", () => {
  // 6048×12256 → uzun kenar 4096'yı aşar; 1:1 basamağı gizlenir ve merdiven [1,2]'de kalır.
  const dev: SahneSayfasi[] = [sayfa("07_combined", "Birleşik", 6048, 12256)];
  const api = render(<GorselSahne sayfalar={dev} tavanY={400} />);
  olc(api);
  fireEvent.press(api.getByTestId("gorsel-sahne-tam-ekran"));
  fireEvent.press(api.getByTestId("gorsel-sahne-yakinlastir"));
  fireEvent.press(api.getByTestId("gorsel-sahne-yakinlastir"));
  expect(api.getByTestId("gorsel-sahne-zoom-etiket").props.children).toBe("%200");
});

test("sayfa degisince zoom SIFIRLANIR", () => {
  // Aksi halde yeni panel rastgele bir yakınlıkta açılır ve kullanıcı kaybolur.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  fireEvent.press(api.getByTestId("gorsel-sahne-tam-ekran"));
  fireEvent.press(api.getByTestId("gorsel-sahne-yakinlastir"));
  fireEvent.press(api.getByTestId("gorsel-sahne-tam-ekran-kapat"));
  fireEvent.press(api.getByTestId("gorsel-sahne-cip-03_phantom_mask"));
  fireEvent.press(api.getByTestId("gorsel-sahne-tam-ekran"));
  expect(api.getByTestId("gorsel-sahne-zoom-etiket").props.children).toBe("%100");
});

// ============================================================================
// 6. ⚠️ ERİŞİLEBİLİRLİK (G13) — ÇİP ROLÜ DEĞİŞMEZ
// ============================================================================

test("KRITIK: cipler Chip bileseni uzerinden cizilir (dokunma tabani + secili durumu)", () => {
  // ⚠️ Ham `TouchableOpacity` yazmak dokunma-hedefi borcunu artırır ve seçili durumu ekran
  // okuyucuya bildirmezdi (renk tek başına yetmez).
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  const aktif = api.getByTestId("gorsel-sahne-cip-06_predictions");
  expect(aktif.props.accessibilityState.selected).toBe(true);
  expect(aktif.props.accessibilityRole).toBe("button"); // G13: 'tab' DEĞİL
  expect(api.getByTestId("gorsel-sahne-cip-01_input").props.accessibilityState.selected).toBe(false);
});

test("KRITIK: oklar ve tam ekran EKRAN OKUYUCU etiketi tasir", () => {
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  expect(api.getByTestId("gorsel-sahne-onceki").props.accessibilityLabel).toBe("Önceki panel");
  expect(api.getByTestId("gorsel-sahne-sonraki").props.accessibilityLabel).toBe("Sonraki panel");
  expect(api.getByTestId("gorsel-sahne-tam-ekran").props.accessibilityLabel).toBe("Tam ekran");
});
