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
import { act, fireEvent, render } from "@testing-library/react-native";
import { CERCEVE, GorselSahne, KONTROL_TAHMINI } from "@/components/ui/GorselSahne";
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

/**
 * Kabın genişliğini ve kontrol satırının yüksekliğini testin KENDİSİ verir.
 *
 * ⚠️ OLAY DIŞ KABA ATILIR (`getByTestId(testID)`), iç kaba DEĞİL. Ölçüm oraya taşındı: iç kap
 * sonuç gelene kadar BOŞ ve 0 yükseklikte olduğu için ilk `ResizeObserver` geri çağrısı
 * kaçabiliyordu ve sahada görsel HİÇ çizilmiyordu (sahip bildirimi 2026-09-12).
 */
function olc(api: ReturnType<typeof render>, kontrolY = KONTROL_TAHMINI, testID = "gorsel-sahne") {
  fireEvent(api.getByTestId(testID), "layout", {
    nativeEvent: { layout: { width: KAP_W, height: 400 } },
  });
  fireEvent(api.getByTestId(`${testID}-kontrol`), "layout", {
    nativeEvent: { layout: { width: KAP_W, height: kontrolY } },
  });
}

/**
 * Kutunun İÇERİK ölçüsü (çerçeve hariç).
 *
 * ⚠️ React Native `border-box`tur: `width: K` + `borderWidth: 1` verilirse iç alan K-2 olur ve
 * K genişliğindeki görsel her kenardan 1 px KIRPILIR. Bu yüzden bileşen çerçeveyi kutu
 * ölçüsüne EKLİYOR; test de aynı hesabı yapmalı, yoksa 2 px'lik sahte fark ölçer.
 */
function kutuOlcusu(api: ReturnType<typeof render>, testID = "gorsel-sahne") {
  const st = api.getByTestId(`${testID}-kutu`).props.style;
  const duz = Array.isArray(st) ? Object.assign({}, ...st.filter(Boolean)) : st;
  return { width: (duz.width as number) - CERCEVE * 2, height: (duz.height as number) - CERCEVE * 2 };
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

test("KRITIK: boyutu BILINMEYEN sayfa YUKLENINCE oran DUZELIR", () => {
  // ⚠️ Panelsiz modüllerin "Girdi" sayfası yerel dosyadır; sunucu boyut bildirmez. Ölçülmezse
  // kutu 4:3'te kalır ve DİKEY bir telefon fotoğrafı kutunun ~%44'ünü boş bırakır — üstelik bu,
  // sahibin "girdi kayboluyor" şikâyeti için açtığımız sayfanın ta kendisi.
  //
  // ⚠️ `Image.getSize` DEĞİL `onLoad` kullanılıyor: getSize native modüle dayanıyor ve o yoksa
  // SENKRON fırlatıp tüm sahneyi çökertiyordu (bu turda ölçüldü). `onLoad` gerçekten sürülebilir.
  //
  // MUTASYON: `onLoad` dalını kaldır → KIRMIZI (oran 4:3'te kalır).
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  fireEvent.press(api.getByTestId("gorsel-sahne-cip-01_input"));
  const once = kutuOlcusu(api);
  expect(once.width / once.height).toBeCloseTo(4 / 3, 1); // yön varsayılanı

  fireEvent(api.getByTestId("gorsel-sahne-gorsel-sahne"), "load", {
    nativeEvent: { source: { width: 3024, height: 4032 } }, // dikey telefon fotoğrafı
  });
  const sonra = kutuOlcusu(api);
  expect(sonra.width / sonra.height).toBeCloseTo(3024 / 4032, 1);
});

test("KRITIK: sunucu boyut BILDIRDIYSE olcum HIC ALINMAZ", () => {
  // ⚠️ Sunucunun boyutu KODLANAN kareye aittir ve oran kilidinin tek kaynağıdır; tarayıcının
  // bildirdiği ham boyut onu ezerse istemci farklı bir kutu çizer ve işaretler kayar.
  //
  // ⚠️ MEKANİZMA `??` SIRASI DEĞİL, `onLoad` KANCASININ HİÇ BAĞLANMAMASIDIR — bu ayrımı mutasyon
  // ölçümü gösterdi: `sayfa?.image_w ?? _olcu?.w` sırasını TERS çevirmek YEŞİL kalıyor, çünkü
  // sunucu boyutu varken `_olcu` zaten hiç dolmuyor. Yani sıra gereksiz ikinci savunmadır;
  // asıl kapı buradaki `onLoad === undefined` iddiasıdır.
  //
  // MUTASYON: `sayfa.image_w ? undefined : handler` guard'ını kaldırıp kancayı her zaman bağla
  // → KIRMIZI.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  const once = kutuOlcusu(api); // "Tahmin" 1200x400
  expect(api.getByTestId("gorsel-sahne-gorsel-sahne").props.onLoad).toBeUndefined();

  fireEvent(api.getByTestId("gorsel-sahne-gorsel-sahne"), "load", {
    nativeEvent: { source: { width: 100, height: 900 } },
  });
  expect(kutuOlcusu(api)).toEqual(once);
});

test("KRITIK: OLCUM HIC GELMESE BILE gorsel CIZILIR", () => {
  // ⚠️ SAHADA ÖLÇÜLEN ARIZA (2026-09-12, sahip bildirimi + ekran görüntüsü): çipler ve sayaç
  // görünüyordu ama GÖRSEL YOKTU; modülü kapatıp açınca geliyordu. Sebep: ölçüm boş bir iç
  // kaptan alınıyordu, ilk `ResizeObserver` geri çağrısı kaçınca `kutu` null kalıyor ve
  // `null` çizildiği için EKRANDA HİÇBİR ŞEY olmuyordu. Kullanıcı analizin çalışmadığını sandı.
  //
  // ⚠️ KURAL: ölçüm gecikse/kaçsa bile "hiçbir şey gösterme" KABUL EDİLEMEZ.
  //
  // MUTASYON: ölçümsüz dalı `: null`a geri çevir → KIRMIZI.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  // Bilerek HİÇBİR layout olayı ateşlenmiyor.
  const gorsel = api.getByTestId("gorsel-sahne-gorsel-sahne");
  expect(gorsel.props.source.uri).toBe(YEDI[5].uri); // varsayılan sayfa: Tahmin
  expect(api.getByTestId("gorsel-sahne-kutu-olcumsuz")).toBeTruthy();
});

test("KRITIK: OLCUM her zaman ICERIGI OLAN dis kaptan alinir", () => {
  // ⚠️ Ölçüm boş bir iç kaptan alınırsa (sonuç gelene kadar 0 yükseklik) ilk `ResizeObserver`
  // geri çağrısı kaçabiliyor ve genişlik 0'da kalıyor — sahada tam bu yaşandı. Dış kap kontrol
  // satırını içerdiği için HER ZAMAN gerçek bir boyuta sahiptir.
  //
  // MUTASYON: `onLayout`u iç kaba (`styles.kap`) geri taşı → KIRMIZI.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  expect(typeof api.getByTestId("gorsel-sahne").props.onLayout).toBe("function");
});

test("KRITIK: OLCUM GELINCE oran-kilitli kutuya GECILIR", () => {
  // Yedek dal kalıcı olsaydı oran kilidi hiç devreye girmez, işaretler kayardı.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  expect(api.queryByTestId("gorsel-sahne-kutu")).toBeNull();
  olc(api);
  expect(api.queryByTestId("gorsel-sahne-kutu-olcumsuz")).toBeNull();
  expect(api.getByTestId("gorsel-sahne-kutu")).toBeTruthy();
});

test("KRITIK: PENCERE YENIDEN BOYUTLANINCA kutu genisligi TAKIP EDER", () => {
  // ⚠️ ÖLÇÜLEN KUSUR (bu tur): ilk yazımda genişlik `eski > 0 ? eski : w` ile KİLİTLENİYORDU.
  // Gerekçe `AiProPanel`den kopyalanmıştı — orada ölçülen kabın KENDİSİ daraldığı için döngü
  // riski var. Burada ölçülen kap `width: "100%"` ve kutu onun ÇOCUĞU → döngü YOK.
  // Kilitli kalsaydı launcher penceresi küçültüldüğünde `useStageHeight` yüksekliği canlı
  // daraltırken genişlik eski değerde kalır, kutu yatayda TAŞARDI.
  //
  // MUTASYON: `setKapW((eski) => (eski > 0 ? eski : w))`a geri dön → KIRMIZI.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  const genis = kutuOlcusu(api);

  fireEvent(api.getByTestId("gorsel-sahne"), "layout", { nativeEvent: { layout: { width: 400, height: 400 } } });
  const dar = kutuOlcusu(api);

  expect(dar.width).toBeLessThan(genis.width);
  expect(dar.width).toBeLessThanOrEqual(400);
});

test("KRITIK: CERCEVE kutu olcusune EKLENIR, gorseli KIRPMAZ", () => {
  // ⚠️ React Native `border-box`tur: `width: K` + `borderWidth: 1` iç alanı K-2 yapar ve
  // K genişliğindeki görsel her kenardan 1 px kırpılır (`overflow: hidden`). Sözleşme
  // "taban görsel ile üst katman AYNI sayısal kutuyu alır" diyor; iç alanın 2 px küçük olması
  // onu sessizce bozardı.
  //
  // MUTASYON: `kutu.width + CERCEVE * 2` yerine `kutu.width` yaz → KIRMIZI.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  const st = api.getByTestId("gorsel-sahne-kutu").props.style;
  const duz = Array.isArray(st) ? Object.assign({}, ...st.filter(Boolean)) : st;
  const gorselStil = api.getByTestId("gorsel-sahne-gorsel-sahne").props.style;
  expect(duz.borderWidth).toBe(CERCEVE);
  expect(duz.width - CERCEVE * 2).toBe(gorselStil.width);
  expect(duz.height - CERCEVE * 2).toBe(gorselStil.height);
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

/** Tam ekranı açar ve modal görünümünün ölçüsünü testin KENDİSİ verir. */
function tamEkranAc(api: ReturnType<typeof render>, gorunum = { width: 1900, height: 1000 }) {
  fireEvent.press(api.getByTestId("gorsel-sahne-tam-ekran"));
  // ⚠️  MODAL İÇİNDE ULAŞMIYOR (RNTL kısıtı: satır içi kapta çalışan
  // aynı çağrı burada handler'ı HİÇ tetiklemiyor — bu turda ölçüldü). Bu yüzden ÜRETİMDEKİ
  // handler doğrudan çağrılıyor; ölçülen davranış aynı, yalnız tetikleme yolu farklı.
  act(() => {
    api.getByTestId("gorsel-sahne-tam-alan").props.onLayout({
      nativeEvent: { layout: { width: gorunum.width, height: gorunum.height } },
    });
  });
}

function tamGorselOlcusu(api: ReturnType<typeof render>) {
  const st = api.getByTestId("gorsel-sahne-gorsel-tam").props.style;
  return { width: st.width as number, height: st.height as number };
}

test("KRITIK: tam ekran %100 = EKRANA SIGDIR (satir ici kutu DEGIL)", () => {
  // ⚠️ SAHİP BİLDİRİMİ (2026-09-12): "100'de de 200'de de aynı, ekstra yakınlaşmıyor".
  // Sebep: tam ekranın taban ölçüsü SATIR İÇİ kutuydu. Satır içi kutu sahne tavanıyla
  // sınırlıdır (~486 px), yani tam ekran zaten "sığdırılmış" değildi: görsel ekranın
  // ortasında küçük duruyor, %200 bile ekranı doldurmuyordu.
  //
  // MUTASYON: `tamTaban`ı `kutu`ya geri çevir → KIRMIZI.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  const satirIci = kutuOlcusu(api);
  tamEkranAc(api, { width: 1900, height: 1000 });

  const tam = tamGorselOlcusu(api);
  expect(tam.height).toBeGreaterThan(satirIci.height * 1.5); // gözle görülür biçimde büyük
  // Ekrana sığdırılmış: iki boyut da görünümü AŞMAZ, en az biri ona DEĞER.
  expect(tam.width).toBeLessThanOrEqual(1900);
  expect(tam.height).toBeLessThanOrEqual(1000);
  expect(Math.max(tam.width / 1900, tam.height / 1000)).toBeCloseTo(1, 1);
});

test("KRITIK: tam ekranda ZOOM olcuyu GERCEKTEN buyutur", () => {
  // ⚠️ Sahibin şikâyetinin ikinci yarısı: düğmeye basınca hiçbir şey değişmiyordu.
  //
  // ⚠️ GÖRÜNÜM BİLEREK KÜÇÜK (600×400): büyük bir görünümde "Tahmin" paneli (1200×400 kaynak)
  // zaten sığdırılırken BÜYÜTÜLÜYOR ve 1:1'i aşmama kuralı gereği yakınlaştırma HAKLI OLARAK
  // yapılmıyor. İlk yazımda test tam da bu yüzden kırmızıydı — kod değil, KURGU yanlıştı.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  tamEkranAc(api, { width: 600, height: 400 }); // sığdırma: 600×200, kaynak 1200 → 1:1 = 2,0

  const once = tamGorselOlcusu(api);
  fireEvent.press(api.getByTestId("gorsel-sahne-yakinlastir"));
  const sonra = tamGorselOlcusu(api);
  expect(sonra.width).toBeGreaterThan(once.width);
  expect(sonra.height / once.height).toBeCloseTo(sonra.width / once.width, 1); // oran korunur
  expect(sonra.width).toBe(1200); // 1:1 = kaynak piksel
});

test("KRITIK: KAYNAK zaten sigdirilmisken yakinlastirma KAPALI", () => {
  // ⚠️ 1:1'i aşmak yalnız bulanıklık üretir; düğme "basılıyor ama bir şey olmuyor" hissi
  // vermemeli. Geniş görünümde 1200 px'lik panel zaten büyütülerek çizilir.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  tamEkranAc(api, { width: 1900, height: 1000 });
  expect(api.getByTestId("gorsel-sahne-yakinlastir").props.accessibilityState.disabled).toBe(true);
  expect(api.getByTestId("gorsel-sahne-zoom-etiket").props.children).toBe("%100");
});

test("KRITIK: tam ekran gorseli KAYDIRILABILIR (transform tasir)", () => {
  // ⚠️ İç içe `ScrollView` terk edildi (yüksekliği sıfıra çöküyordu); kaydırma artık
  // `transform` + sürükleme ile. Dönüşüm yoksa yakınlaştırılan görselin kenarlarına
  // ERİŞİLEMEZ — zoom işe yaramaz hale gelir.
  //
  // MUTASYON: `transform` dizisini kaldır → KIRMIZI.
  const api = render(<GorselSahne sayfalar={YEDI} tavanY={400} />);
  olc(api);
  tamEkranAc(api);
  const st = api.getByTestId("gorsel-sahne-gorsel-tam").props.style;
  expect(Array.isArray(st.transform)).toBe(true);
  expect(st.transform).toEqual([{ translateX: 0 }, { translateY: 0 }]);
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
