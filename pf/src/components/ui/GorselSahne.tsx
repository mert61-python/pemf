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
import { ReactNode, useState } from "react";
import { Image, Modal, ScrollView, StyleSheet, Text, View } from "react-native";
import { ChevronLeft, ChevronRight, Maximize2, Minus, Plus, X } from "lucide-react-native";
import { Chip, ChipRow } from "@/components/ui/Chip";
import { IconButton } from "@/components/ui/IconButton";
import { colors, radius, spacing, touch, typography } from "@/theme/tokens";
import { kameraKutusu, kareOrani } from "@/utils/kameraKutusu";
import type { SahneSayfasi } from "@/utils/gorselSahneSayfalari";
import { varsayilanSayfa } from "@/utils/gorselSahneSayfalari";
import { basamakEtiketi, birebirOrani, oncekiBasamak, sonrakiBasamak, zoomBasamaklari } from "@/utils/zoomMerdiveni";

/**
 * Kontrol satırının ölçülemediği ilk karedeki TAHMİNİ yüksekliği (px).
 * ⚠️ Gerçek değer `onLayout` ile ölçülür; bu yalnız ilk kare için güvenli bir üst tahmindir
 * (ok satırı `touch.min` + çip satırı `touch.sm` + iki boşluk). Sabit bırakılsaydı çipler iki
 * satıra sardığında bütçe yetmez ve içerik yine taşardı.
 */
export const KONTROL_TAHMINI = touch.min + touch.sm + spacing.sm * 2;

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

  // ⚠️ TAVANI HESABIN İÇİNE VER: `Math.min(tavan, kutu.height)` ile SONRADAN kırpmak yüksekliği
  // kırpıp genişliği bırakır → oran yine bozulur (`aspectRatio + maxHeight` tuzağının ikizi).
  const icTavan = Math.max(SAHNE_ASGARI, tavanY - kontrolY);
  const oran = kareOrani({ image_w: sayfa?.image_w, image_h: sayfa?.image_h }, false);
  const kutu = kapW > 0 ? kameraKutusu(kapW, oran, icTavan, 1) : null;

  // ⚠️ `basamaklar` ve `birebir` AYNI girdiden türer — etiket "son basamak tam sayı değilse
  // 1:1'dir" diye TAHMİN etmez (3000/600 = 5,0 gibi tam sayılı bir 1:1'i "%500" yazıyordu).
  const kaynakW = sayfa?.image_w;
  const kaynakH = sayfa?.image_h;
  const kutuW = kutu?.width ?? 0;
  // ⚠️ `useMemo` YOK — bu iki hesap birkaç aritmetik işlem; elle memolamak React Compiler'ın
  // bileşeni optimize etmesini tamamen ENGELLİYORDU (lint: "memoization could not be preserved").
  const basamaklar = zoomBasamaklari({ kaynakW, kaynakH, kutuW });
  const birebir = birebirOrani({ kaynakW, kaynakH, kutuW });

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
      testID={`${testID}-gorsel-${anahtar}`}
      accessibilityLabel={`${sayfa.ad} paneli`}
    />
  );

  return (
    <View testID={testID}>
      <View
        style={styles.kap}
        onLayout={(e) => {
          const w = Math.round(e.nativeEvent.layout.width);
          // Kutu kendi genişliğini de değiştirdiği için yalnız ilk ölçüm alınır
          // (aksi hâlde ölç → daralt → ölç döngüsü kurulur — AiProPanel'de ölçüldü).
          setKapW((eski) => (eski > 0 ? eski : w));
        }}
      >
        {kutu ? (
          <View style={[styles.kutu, { width: kutu.width, height: kutu.height }]} testID={`${testID}-kutu`}>
            {gorsel(kutu, "sahne")}
            {ustKatman?.(kutu)}
          </View>
        ) : null}
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
                onPress={() => setZoom((z) => oncekiBasamak(basamaklar, z))}
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
                onPress={() => setZoom((z) => sonrakiBasamak(basamaklar, z))}
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

          <ScrollView
            style={styles.tamKaydirma}
            contentContainerStyle={styles.tamIcerik}
            maximumZoomScale={1}
            horizontal={false}
          >
            <ScrollView horizontal contentContainerStyle={styles.tamIcerik}>
              {kutu
                ? gorsel({ width: Math.round(kutu.width * zoom), height: Math.round(kutu.height * zoom) }, "tam")
                : null}
            </ScrollView>
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  kap: { width: "100%", alignItems: "center" },
  kutu: {
    alignSelf: "center",
    backgroundColor: colors.bg,
    borderRadius: radius.md,
    borderWidth: 1,
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
  tamKaydirma: { flex: 1 },
  tamIcerik: { justifyContent: "center", alignItems: "center", flexGrow: 1 },
});
