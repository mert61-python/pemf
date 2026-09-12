// Author: mertaygn
/**
 * GÖRSEL SAHNE — gezilebilir, oran-kilitli AI görsel galerisi. [AI Hub planı, ADIM 4]
 * ==================================================================================
 * SAHİBİN BİLDİRDİĞİ İKİ ARIZA (2026-09-09), ikisi de burada kapanır:
 *
 * 1. **GİRDİ KAYBOLUYOR** — `AiHubScreen.tsx`'te BEŞ yerde birebir aynı ternary vardı
 *    (`result?.image_base64 ? 'data:…' : imageUri`). Sonuç gelince kullanıcının fotoğrafı
 *    ekrandan siliniyordu. Artık girdi bir SAYFA: her zaman bir çip uzaklıkta.
 * 2. **SONUÇ OKUNMAZ** — `07_combined` 2×3 mozaik; sahne tavanında panel başına ~81 px kalıyor,
 *    gömülü ~12 px metin ~0,35 px'e iniyordu. Artık paneller TEK TEK, tam sahne boyunda
 *    gösteriliyor; tam ekran + kaynak-piksele kilitli zoom okunabilirliği garanti ediyor.
 *
 * ⚠️ ORAN KİLİDİ TEK KAYNAK: kutu `kameraKutusu()` ile AÇIK px olarak hesaplanır ve
 * `aspectRatio` + `maxHeight` ikilisi KULLANILMAZ (maxHeight yüksekliği kırpınca genişlik %100
 * kaldığı için oran yine bozulur). Taban görsel ile üstüne çizilen katman AYNI sayısal kutuyu
 * alır → organ/tümör işaretleri görüntüyle kaymaz. Bu bir tıbbi karar ekranı.
 *
 * ⚠️ TOPLAM YÜKSEKLİK BÜTÇESİ: kontrol satırı sahne tavanından DÜŞÜLÜR. Demo turunda ölçüldü —
 * sahneye tam `useStageHeight()` verilince 700×540'lık launcher penceresinde içerik taştı ve
 * oklar kırpıldı. Kutu yüksekliğini tek başına ölçen bir kapı bu taşmayı YEŞİL geçer (bkz. G11).
 *
 * ⚠️ SARMA YOK: oklar sınırda durur (`clamp`), `(i+1)%n` DEĞİL. 7 panelde "Birleşik"ten sonra
 * "Girdi"ye atlamak, operatörün kaçıncı panelde olduğunu kaybetmesi demektir; sayaç da yalan söyler.
 */
import { ReactNode, useEffect, useRef, useState } from "react";
import { Image, Modal, PanResponder, StyleSheet, Text, View } from "react-native";
import { ChevronLeft, ChevronRight, Maximize2, Minus, Plus, X } from "lucide-react-native";
import { Chip, ChipRow } from "@/components/ui/Chip";
import { IconButton } from "@/components/ui/IconButton";
import { colors, radius, spacing, touch, typography } from "@/theme/tokens";
import { kameraKutusu, kareOrani } from "@/utils/kameraKutusu";
import type { SahneSayfasi } from "@/utils/gorselSahneSayfalari";
import { varsayilanSayfa } from "@/utils/gorselSahneSayfalari";
import {
  basamakEtiketi,
  birebirOrani,
  oncekiBasamak,
  sonrakiBasamak,
  zoomBasamaklari,
  zoomSinirla,
} from "@/utils/zoomMerdiveni";

/**
 * Kontrol satırının ölçülemediği ilk karedeki TAHMİNİ yüksekliği (px).
 * ⚠️ Gerçek değer `onLayout` ile ölçülür; bu yalnız ilk kare için güvenli bir üst tahmindir
 * (ok satırı `touch.min` + çip satırı `touch.sm` + iki boşluk). Sabit bırakılsaydı çipler iki
 * satıra sardığında bütçe yetmez ve içerik yine taşardı.
 */
export const KONTROL_TAHMINI = touch.min + touch.sm + spacing.sm * 2;

/** Kutu çerçevesi (px) — RN border-box olduğu için kutu ölçüsüne EKLENİR (bkz. çizim). */
export const CERCEVE = 1;

/** Kutu bu yüksekliğin altına inmez — tanınmayacak kadar küçük sahne işe yaramaz. */
export const SAHNE_ASGARI = 120;

export interface GorselSahneProps {
  /** Gezilecek sayfalar (`sahneSayfalari()` üretir). Boşsa `bos` gösterilir. */
  sayfalar: SahneSayfasi[];
  /** Sahne yüksekliği tavanı — çağıran `useStageHeight()` verir. */
  tavanY: number;
  /**
   * Değişince sayfa indeksi varsayılana DÖNER. Yeni analiz / canlıya geçiş / yeni fotoğraf.
   * ⚠️ Sıfırlanmazsa 7 panelli bir analizden 2 sayfalı bir sonuca geçince indeks aralık
   * dışında kalır ve ekran boşalır; ayrıca eski sonucun izi yeni analizde görünür.
   */
  sifirlaAnahtari?: string | number | null;
  /** Görsel yokken gösterilecek düğüm. */
  bos?: ReactNode;
  /**
   * Taban görselin ÜSTÜNE çizilen katman. AYNI sayısal kutuyu alır (organ işareti hizası).
   * ⚠️ `{width:'100%',height:'100%'}` VERMEYİN — kap oran-kilitsiz kalırsa işaretler kayar.
   */
  ustKatman?: (kutu: { width: number; height: number }) => ReactNode;
  testID?: string;
}

export function GorselSahne({ sayfalar, tavanY, sifirlaAnahtari, bos, ustKatman, testID = "gorsel-sahne" }: GorselSahneProps) {
  const [indeks, setIndeks] = useState(() => varsayilanSayfa(sayfalar));
  const [kapW, setKapW] = useState(0);
  const [kontrolY, setKontrolY] = useState(KONTROL_TAHMINI);
  const [tamEkran, setTamEkran] = useState(false);
  const [zoom, setZoom] = useState(1);

  const adet = sayfalar.length;

  // ⚠️ YENİ ANALİZ → VARSAYILAN SAYFAYA DÖN. Sayfa listesi değişince indeks aralık dışında da
  // kalabilir; ikisi tek imzada toplanır.
  //
  // ⚠️ `useEffect` DEĞİL, RENDER SIRASINDA sıfırlanır (React'in "prop değişince state'i ayarla"
  // deseni). Efektle yapılsaydı ARADA BİR KARE eski sayfa çizilirdi: canlı kameraya geçerken
  // önceki analizin overlay'i bir kare boyunca görünür kalır — `catOrganCanliKalinti` kapısının
  // tam olarak yasakladığı şey. Ayrıca efekt içinde setState zincirleme render uyarısı üretir.
  const imza = `${sifirlaAnahtari ?? ""}|${adet}`;
  const [oncekiImza, setOncekiImza] = useState(imza);
  if (imza !== oncekiImza) {
    setOncekiImza(imza);
    setIndeks(varsayilanSayfa(sayfalar));
    setTamEkran(false);
    setZoom(1);
  }

  const guvenliIndeks = adet > 0 ? Math.min(Math.max(indeks, 0), adet - 1) : 0;
  const sayfa = sayfalar[guvenliIndeks];

  // ⚠️ BOYUTU BİLİNMEYEN SAYFAYI ÖLÇ (panelsiz modüllerin "Girdi" sayfası: yerel dosya, sunucu
  // bir şey bildirmiyor). Ölçülmezse kutu yön varsayılanına (4:3) düşer ve dikey bir telefon
  // fotoğrafı kutunun ~%44'ünü boş bırakır — sonuç panellerinin yanında bozuk görünür.
  //
  // ⚠️ `Image.getSize` DENENDİ VE TERK EDİLDİ: RN'in iOS uygulaması `ImageViewManager.getSize`
  // native modülüne dayanıyor ve o yoksa SENKRON FIRLATIYOR ("Cannot read properties of
  // undefined (reading 'then')") — testlerde tüm sahneyi çökertti; `try/catch` de yetmedi,
  // çünkü sahte modül hatayı SONRAKİ TICK'te atıyor. Üstelik test ortamında sahteyle ölçülen
  // bir kapı hiçbir şey kanıtlamazdı.
  //
  // ⚠️ YERİNE `onLoad`: çizilen görselin KENDİ yükleme olayı. Native modül gerektirmez, web'de
  // de çalışır ve testte `fireEvent(gorsel, "load", …)` ile GERÇEKTEN sürülebilir. Bedeli tek
  // kare: ilk çizim yön varsayılanında, yükleme bitince oran düzelir (`contain` olduğu için
  // o karede de görüntü BOZULMAZ, yalnız kenarda boşluk kalır).
  const [olculen, setOlculen] = useState<Record<string, { w: number; h: number }>>({});
  const olcumAl = (k: string, w?: number, h?: number) => {
    if (!(typeof w === "number" && typeof h === "number" && w > 0 && h > 0)) return;
    setOlculen((o) => (o[k] ? o : { ...o, [k]: { w, h } }));
  };

  // ⚠️ TAVANI HESABIN İÇİNE VER: `Math.min(tavan, kutu.height)` ile SONRADAN kırpmak yüksekliği
  // kırpıp genişliği bırakır → oran yine bozulur (`aspectRatio + maxHeight` tuzağının ikizi).
  const icTavan = Math.max(SAHNE_ASGARI, tavanY - kontrolY);
  const _olcu = sayfa ? olculen[sayfa.k] : undefined;
  const oran = kareOrani(
    { image_w: sayfa?.image_w ?? _olcu?.w, image_h: sayfa?.image_h ?? _olcu?.h },
    false,
  );
  const kutu = kapW > 0 ? kameraKutusu(kapW, oran, icTavan, 1) : null;

  // ⚠️ `basamaklar` ve `birebir` AYNI girdiden türer — etiket "son basamak tam sayı değilse
  // 1:1'dir" diye TAHMİN etmez (3000/600 = 5,0 gibi tam sayılı bir 1:1'i "%500" yazıyordu).
  // ⚠️ ÖLÇÜLEN BOYUT ZOOM MERDİVENİNE DE GİRER: yerel dosya gerçekten o çözünürlükte, dolayısıyla
  // 1:1 basamağı onun için de anlamlıdır. (4096 px doku sınırı kontrolü zaten merdivende.)
  const kaynakW = sayfa?.image_w ?? _olcu?.w;
  const kaynakH = sayfa?.image_h ?? _olcu?.h;
  // ⚠️ `useMemo` YOK — bu iki hesap birkaç aritmetik işlem; elle memolamak React Compiler'ın
  // bileşeni optimize etmesini tamamen ENGELLİYORDU (lint: "memoization could not be preserved").
  // ══════════════════════════════════════════════════════════════════════════════════════════
  // TAM EKRAN GÖRÜNTÜLEYİCİ
  // ⚠️ TABAN ÖLÇÜ TAM EKRAN GÖRÜNÜMÜNDEN GELİR, satır içi kutudan DEĞİL. Satır içi kutu
  // kullanıldığında tam ekran "sığdırılmış" olmuyordu: görsel ekranın ortasında küçük duruyor ve
  // %200'e basınca gözle fark edilmiyordu (sahip bildirimi: "100'de de 200'de de aynı").
  // Artık %100 = EKRANA SIĞDIR, üst basamaklar oradan büyür.
  // ══════════════════════════════════════════════════════════════════════════════════════════
  const [gorunum, setGorunum] = useState({ w: 0, h: 0 });
  const [kaydirma, setKaydirma] = useState({ x: 0, y: 0 });
  const tamAlanRef = useRef(null);
  // ⚠️ "EN SON DEĞER" REF'LERİ: tekerlek dinleyicisi ve  bir kez kurulur; kapanışta
  // eski state'i görmemeleri için güncel değerler ref'te tutulur. ⚠️ Yazma RENDER SIRASINDA
  // DEĞİL EFEKTTE olur — React Compiler render sırasında ref yazmayı yasaklıyor (lint hatası).
  const zoomRef = useRef(1);
  const kaydirmaRef = useRef({ x: 0, y: 0 });
  const baslangicRef = useRef({ x: 0, y: 0 });
  const tamTabanRef = useRef<{ width: number; height: number } | null>(null);
  const sinirlaRef = useRef<(n: { x: number; y: number }, o: { width: number; height: number } | null) => { x: number; y: number }>(() => ({ x: 0, y: 0 }));

  const tamTaban = gorunum.w > 0 && gorunum.h > 0 ? kameraKutusu(gorunum.w, oran, gorunum.h, 1) : kutu;
  const tamOlcu = tamTaban
    ? { width: Math.round(tamTaban.width * zoom), height: Math.round(tamTaban.height * zoom) }
    : null;

  // ⚠️ KAYDIRMA SINIRLANIR: aksi hâlde görsel ekrandan tamamen çıkıp "kayboluyor" sanılır.
  // Görsel görünümden küçükse kaydırma SIFIRDIR (ortada durur).
  const sinirla = (n: { x: number; y: number }, olcu: { width: number; height: number } | null) => {
    if (!olcu) return { x: 0, y: 0 };
    const sx = Math.max(0, (olcu.width - gorunum.w) / 2);
    const sy = Math.max(0, (olcu.height - gorunum.h) / 2);
    return { x: Math.min(sx, Math.max(-sx, n.x)), y: Math.min(sy, Math.max(-sy, n.y)) };
  };

  const basamaklar = zoomBasamaklari({ kaynakW, kaynakH, kutuW: tamTaban?.width ?? 0 });
  const birebir = birebirOrani({ kaynakW, kaynakH, kutuW: tamTaban?.width ?? 0 });

  // ⚠️ REF'LER EFEKTTE EŞİTLENİR (render sırasında DEĞİL): tekerlek dinleyicisi ve `PanResponder`
  // bir kez kurulur; kapanışta eski state'i görmemeleri için en son değerleri buradan okurlar.
  // Bağımlılık dizisi YOK — her render sonrası eşitlenir.
  useEffect(() => {
    zoomRef.current = zoom;
    kaydirmaRef.current = kaydirma;
    tamTabanRef.current = tamTaban;
    sinirlaRef.current = sinirla;
  });

  /** Zoom'u sınırlar içinde değiştirir ve kaydırmayı yeni ölçeğe göre toparlar. */
  const zoomla = (yeni: number) => {
    const z = zoomSinirla(yeni, birebir, basamaklar);
    setZoom(z);
    if (tamTaban) {
      setKaydirma((k) => sinirla(k, { width: tamTaban.width * z, height: tamTaban.height * z }));
    }
  };

  // ⚠️ FARE TEKERLEĞİ = YAKINLAŞTIRMA (sahip isteği: "farenin scrolluyla yakınlaştırıp
  // uzaklaştıramaz mıyım, daha kullanıcı dostu olmaz mı"). RN'de `onWheel` PROP'U YOKTUR;
  // web'de DOM düğümüne doğrudan bağlanır. `passive: false` ŞART, yoksa `preventDefault`
  // yok sayılır ve sayfa tekerlekle kayar.
  // ⚠️ Native'de sessizce atlanır (düğüme `addEventListener` yoktur) — düğmeler zaten var.
  useEffect(() => {
    if (!tamEkran) return;
    const dugum = tamAlanRef.current as unknown as {
      addEventListener?: (t: string, f: (e: WheelEvent) => void, o?: AddEventListenerOptions) => void;
      removeEventListener?: (t: string, f: (e: WheelEvent) => void) => void;
    } | null;
    if (!dugum?.addEventListener) return;
    const f = (e: WheelEvent) => {
      e.preventDefault();
      zoomla(zoomRef.current * (e.deltaY < 0 ? 1.15 : 1 / 1.15));
    };
    dugum.addEventListener("wheel", f, { passive: false });
    return () => dugum.removeEventListener?.("wheel", f);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tamEkran, tamTaban?.width, tamTaban?.height, birebir]);


  // ⚠️ SÜRÜKLEYEREK GEZ: yakınlaştırıldığında görüntünün her yerine erişilebilmeli. İç içe
  // `ScrollView` yerine `transform` kullanıldığı için kaydırmayı bu sağlar.
  // ⚠️  baslatici ile BIR KEZ kurulur:  render sirasinda ref
  // okumak olur ve React Compiler bunu uyarir.
  const [tasiyici] = useState(() =>
    PanResponder.create({
      onMoveShouldSetPanResponder: (_e, g) => Math.abs(g.dx) > 2 || Math.abs(g.dy) > 2,
      onPanResponderMove: (_e, g) => {
        const t = tamTabanRef.current;
        if (!t) return;
        const z = zoomRef.current;
        setKaydirma(
          sinirlaRef.current({ x: baslangicRef.current.x + g.dx, y: baslangicRef.current.y + g.dy },
            { width: t.width * z, height: t.height * z }),
        );
      },
      onPanResponderGrant: () => {
        baslangicRef.current = kaydirmaRef.current;
      },
    }),
  );

  if (adet === 0) return <>{bos ?? null}</>;

  const git = (yon: -1 | 1) => {
    // ⚠️ CLAMP, SARMA DEĞİL (yukarıdaki gerekçe).
    setIndeks((i) => Math.min(Math.max(i + yon, 0), adet - 1));
    setZoom(1);
  };

  const gorsel = (kutuOlcu: { width: number; height: number }, anahtar: string) => (
    <Image
      // ⚠️ AÇIK SAYISAL KUTU — `{width:'100%',height:'100%'}` DEĞİL: üst katman da aynı sayıları
      // alır, böylece işaret hizası korunur.
      source={{ uri: sayfa.uri }}
      style={{ width: kutuOlcu.width, height: kutuOlcu.height }}
      resizeMode="contain"
      // ⚠️ Yalnız boyutu BİLİNMEYEN sayfa için ölçüm alınır; sunucu bildirdiyse ona dokunulmaz
      // (sunucunun boyutu KODLANAN kareye aittir ve oran kilidinin tek kaynağıdır).
      onLoad={
        sayfa.image_w
          ? undefined
          : (e) => {
              const k = (e?.nativeEvent as { source?: { width?: number; height?: number } } | undefined)?.source;
              olcumAl(sayfa.k, k?.width, k?.height);
            }
      }
      testID={`${testID}-gorsel-${anahtar}`}
      accessibilityLabel={`${sayfa.ad} paneli`}
    />
  );

  return (
    // ⚠️ ÖLÇÜM BURADA, İÇ KAPTA DEĞİL — SAHADA ÖLÇÜLEN ARIZA (2026-09-12, sahip bildirimi):
    // görsel HİÇ çizilmiyordu, modülü kapatıp açınca geliyordu. Sebep: ölçülen iç kap
    // (`styles.kap`) sonuç gelene kadar BOŞ ve yüksekliği 0 olan bir kutuydu; ilk
    // `ResizeObserver` geri çağrısı kaçırıldığında genişlik 0'da kalıyor ve `kutu` null
    // olduğu için EKRANA HİÇBİR ŞEY çizilmiyordu. Bu dış kap kontrol satırını içerdiği için
    // HER ZAMAN gerçek bir boyuta sahiptir; ölçüm kaçmaz.
    // ⚠️ Döngü yok: kutunun genişliği daima ölçülen genişlikten KÜÇÜK EŞİTTİR
    // (`kameraKutusu` yüksekliği kapa göre sınırlar), dolayısıyla dış kabı büyütemez.
    <View
      testID={testID}
      style={styles.dis}
      onLayout={(e) => {
        const w = Math.round(e.nativeEvent.layout.width);
          // ⚠️ HER ÖLÇÜMDE GÜNCELLENİR — "yalnız ilk ölçüm" DEĞİL. `AiProPanel`de ölç → daralt →
          // ölç döngüsünü önlemek için ilk ölçüm kilitleniyor; oradaki gerekçe ÖLÇÜLEN kabın
          // KENDİSİNİN daralmasıydı. Burada ölçülen kap `width: "100%"` ve kutu onun ÇOCUĞU →
          // kutunun genişliği ölçülen genişliği ETKİLEYEMEZ, dolayısıyla döngü yok.
          // ⚠️ Kilitli bırakılsaydı pencere yeniden boyutlandığında (launcher penceresi, cihaz
          // yan yatması) `useStageHeight` yüksekliği CANLI daraltırken genişlik ESKİ değerde
          // kalır → kutu yatayda taşar ya da kenarda boşluk bırakır. Sahnenin canlı olması bu
          // bileşenin var oluş gerekçelerinden biri.
        if (w > 0) setKapW((eski) => (Math.abs(eski - w) >= 1 ? w : eski));
      }}
    >
      <View style={styles.kap}>
        {kutu ? (
          // ⚠️ ÇERÇEVE GENİŞLİĞE EKLENİR, İÇİNDEN GİTMEZ. React Native'de kutu modeli
          // `border-box`: `width: K` + `borderWidth: 1` verirsen İÇ ALAN K-2 olur ve K
          // genişliğindeki görsel her kenardan 1 px KIRPILIR (`overflow: hidden`). Kırpılan
          // sadece bir çizgi ama sözleşme "taban görsel ile üst katman AYNI sayısal kutuyu alır"
          // diyor; iç alanın 2 px küçük olması o sözleşmeyi sessizce bozardı.
          <View
            style={[styles.kutu, { width: kutu.width + CERCEVE * 2, height: kutu.height + CERCEVE * 2 }]}
            testID={`${testID}-kutu`}
          >
            {gorsel(kutu, "sahne")}
            {ustKatman?.(kutu)}
          </View>
        ) : (
          // ⚠️ ÖLÇÜM GELMEDEN DE GÖRSEL ÇİZİLİR — "hiçbir şey gösterme" KABUL EDİLEMEZ.
          // Sahada tam bu yaşandı: ölçüm kaçınca ekranda görsel YOKTU ve kullanıcı analizin
          // çalışmadığını sandı. Bu dalda oran kilidi YOK (kutu bilinmiyor), yalnız yükseklik
          // sınırlı: `contain` olduğu için görüntü BOZULMAZ, en fazla kenarda boşluk kalır.
          // Ölçüm gelir gelmez yukarıdaki oran-kilitli dala geçilir.
          <View style={[styles.kutu, styles.olcumsuz, { height: icTavan }]} testID={`${testID}-kutu-olcumsuz`}>
            <Image
              source={{ uri: sayfa.uri }}
              style={styles.olcumsuzGorsel}
              resizeMode="contain"
              testID={`${testID}-gorsel-sahne`}
              accessibilityLabel={`${sayfa.ad} paneli`}
            />
          </View>
        )}
      </View>

      <View
        style={styles.kontrol}
        onLayout={(e) => setKontrolY(Math.round(e.nativeEvent.layout.height))}
        testID={`${testID}-kontrol`}
      >
        <View style={styles.okSatiri}>
          <IconButton
            label="Önceki panel"
            onPress={() => git(-1)}
            disabled={guvenliIndeks === 0}
            testID={`${testID}-onceki`}
            style={styles.ok}
          >
            <ChevronLeft color={guvenliIndeks === 0 ? colors.textSubtle : colors.text} size={20} />
          </IconButton>

          {/* ⚠️ `typography.small` (11) — rf(9) gibi daha küçük bir punto "okunmaz yazı"
              şikâyetinin ta kendisiydi; sayacı küçültmek çözüm olamaz. */}
          <Text style={styles.sayac} testID={`${testID}-sayac`}>
            {sayfa.ad} · {guvenliIndeks + 1}/{adet}
          </Text>

          <IconButton
            label="Sonraki panel"
            onPress={() => git(1)}
            disabled={guvenliIndeks === adet - 1}
            testID={`${testID}-sonraki`}
            style={styles.ok}
          >
            <ChevronRight color={guvenliIndeks === adet - 1 ? colors.textSubtle : colors.text} size={20} />
          </IconButton>

          <IconButton
            label="Tam ekran"
            accessibilityHint="Paneli büyütüp yakınlaştırarak açar"
            onPress={() => {
              setTamEkran(true);
              setZoom(1);
            }}
            testID={`${testID}-tam-ekran`}
            style={styles.ok}
          >
            <Maximize2 color={colors.text} size={18} />
          </IconButton>
        </View>

        {/* ⚠️ `Chip` kullanılıyor: dokunma tabanı (touch.sm) ve `accessibilityState.selected`
            tek kaynaktan gelir. Ham `TouchableOpacity` yazmak dokunma-hedefi borcunu artırırdı. */}
        <ChipRow style={styles.cipler}>
          {sayfalar.map((s, i) => (
            <Chip
              key={s.k}
              label={s.ad}
              active={i === guvenliIndeks}
              onPress={() => {
                setIndeks(i);
                setZoom(1);
              }}
              style={styles.cip}
              activeStyle={styles.cipAktif}
              textStyle={styles.cipMetin}
              activeTextStyle={styles.cipMetinAktif}
              testID={`${testID}-cip-${s.k}`}
            />
          ))}
        </ChipRow>
      </View>

      <Modal visible={tamEkran} transparent={false} animationType="fade" onRequestClose={() => setTamEkran(false)}>
        <View style={styles.tamKap} testID={`${testID}-tam-ekran-kap`}>
          <View style={styles.tamBaslik}>
            <Text style={styles.tamAd} numberOfLines={1}>
              {sayfa.ad} · {guvenliIndeks + 1}/{adet}
            </Text>
            <View style={styles.tamAraclar}>
              <IconButton
                label="Uzaklaştır"
                onPress={() => zoomla(oncekiBasamak(basamaklar, zoomRef.current))}
                disabled={basamaklar.length < 2}
                testID={`${testID}-uzaklastir`}
                style={styles.ok}
              >
                <Minus color={colors.text} size={18} />
              </IconButton>
              <Text style={styles.zoomEtiket} testID={`${testID}-zoom-etiket`}>
                {basamakEtiketi(zoom, birebir)}
              </Text>
              <IconButton
                label="Yakınlaştır"
                onPress={() => zoomla(sonrakiBasamak(basamaklar, zoomRef.current))}
                disabled={basamaklar.length < 2}
                testID={`${testID}-yakinlastir`}
                style={styles.ok}
              >
                <Plus color={colors.text} size={18} />
              </IconButton>
              {/* ⚠️ Kapanışta SAYFA İNDEKSİ KORUNUR — sıfırlamak, operatörün 7 panel içinde
                  bulduğu yeri her tam ekran kapanışında kaybetmesi demekti. */}
              <IconButton label="Kapat" onPress={() => setTamEkran(false)} testID={`${testID}-tam-ekran-kapat`} style={styles.ok}>
                <X color={colors.text} size={20} />
              </IconButton>
            </View>
          </View>

          {/* ⚠️ İÇ İÇE `ScrollView` TERK EDİLDİ. Önce yatay kaydırıcının yüksekliği sıfıra
              çöküyordu (görsel hiç çizilmedi); açık yükseklik verince çizildi ama ZOOM İŞE
              YARAMIYORDU: taban ölçü SATIR İÇİ kutuydu, yani tam ekran zaten "sığdırılmış"
              değildi ve %200 gözle fark edilmiyordu. Ayrıca kaydırıcıların ortalanmış içerik
              kabı, içerik taşınca üst kenarı ERİŞİLEMEZ yapıyordu.
              ⚠️ YERİNE: kırpan tek bir kap + `transform` ile ölçekleme/kaydırma. Taban ölçü
              TAM EKRAN GÖRÜNÜMÜNDEN hesaplanır (zoom %100 = ekrana SIĞDIR), tekerlek sürekli
              yakınlaştırır, sürükleme kaydırır. Sahibin istediği "fotoğraf görüntüleyici" davranışı. */}
          <View
            ref={tamAlanRef}
            style={styles.tamAlan}
            testID={`${testID}-tam-alan`}
            onLayout={(e) => {
              const { width, height } = e.nativeEvent.layout;
              setGorunum((g) => (Math.abs(g.w - width) >= 1 || Math.abs(g.h - height) >= 1 ? { w: width, h: height } : g));
            }}
            {...tasiyici.panHandlers}
          >
            {tamOlcu ? (
              <Image
                source={{ uri: sayfa.uri }}
                style={{
                  width: tamOlcu.width,
                  height: tamOlcu.height,
                  transform: [{ translateX: kaydirma.x }, { translateY: kaydirma.y }],
                }}
                resizeMode="contain"
                testID={`${testID}-gorsel-tam`}
                accessibilityLabel={`${sayfa.ad} paneli`}
              />
            ) : (
              // Ölçüm gelmemişse yine de göster (satır içi yedek çizimin tam ekran ikizi).
              <Image
                source={{ uri: sayfa.uri }}
                style={styles.olcumsuzGorsel}
                resizeMode="contain"
                testID={`${testID}-gorsel-tam`}
                accessibilityLabel={`${sayfa.ad} paneli`}
              />
            )}
          </View>
          <Text style={styles.tamIpucu}>Tekerlekle yakınlaştır · sürükleyerek gez</Text>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  dis: { width: "100%" },
  kap: { width: "100%", alignItems: "center" },
  // Ölçüm gelmeden çizilen yedek kutu: oran kilidi YOK, yalnız yükseklik sınırlı.
  olcumsuz: { width: "100%" },
  olcumsuzGorsel: { width: "100%", height: "100%" },
  kutu: {
    alignSelf: "center",
    backgroundColor: colors.bg,
    borderRadius: radius.md,
    borderWidth: CERCEVE,
    borderColor: colors.border,
    overflow: "hidden",
  },
  kontrol: { marginTop: spacing.sm, gap: spacing.sm },
  okSatiri: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  ok: { backgroundColor: colors.panelSoft, borderRadius: radius.md, paddingHorizontal: spacing.sm },
  sayac: { flex: 1, textAlign: "center", color: colors.textMuted, fontSize: typography.small, fontWeight: "600" },
  cipler: { justifyContent: "center" },
  cip: { backgroundColor: colors.panelSoft, paddingVertical: spacing.xs, paddingHorizontal: spacing.sm },
  cipAktif: { backgroundColor: colors.primarySoft },
  cipMetin: { color: colors.textMuted },
  cipMetinAktif: { color: colors.text },
  tamKap: { flex: 1, backgroundColor: colors.bg },
  tamBaslik: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  tamAd: { flex: 1, color: colors.text, fontSize: typography.body, fontWeight: "700" },
  tamAraclar: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  zoomEtiket: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700", minWidth: 44, textAlign: "center" },
  // Kirpan kap: gorsel transform ile buyur/kayar, tasan kisim gizlenir.
  tamAlan: { flex: 1, overflow: "hidden", alignItems: "center", justifyContent: "center" },
  tamIpucu: { color: colors.textSubtle, fontSize: typography.small, textAlign: "center", paddingVertical: spacing.xs },
  tamKaydirma: { flex: 1 },
  tamIcerik: { justifyContent: "center", alignItems: "center", flexGrow: 1 },
  // ⚠️ flexGrow YOK: yatay kaydiricinin yuksekligi ACIK verildigi icin buyumesi gerekmez.
  tamYatay: { alignItems: "center", justifyContent: "center" },
});
