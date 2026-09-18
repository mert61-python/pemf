// Author: mertaygn
/**
 * GENİŞLETİLEBİLİR METİN — "üç noktadan sonrası okunamıyor" (sahip bildirimi 2026-09-12).
 * =====================================================================================
 * "bildirim sığmayınca üç noktadan sonrasını kullanıcı hiçbir şekilde okuyamıyor,
 *  bildirimin üzerine tıklayınca tamamının açılması lazım aslında."
 * "ai analiz detaylarında yine üç nokta sorunu ... bunların üzerine tıklayınca tam metni
 *  gösterme özelliği kazandırılmalı diye düşünüyorum kullanıcı dostu bir çözüm üret."
 *
 * ═══════════════════════════════════════════════════════════════════════════════
 * SÖZLEŞME
 * ═══════════════════════════════════════════════════════════════════════════════
 * · Kapalıyken `satir` satırda kırpılır (eski görünüm BİREBİR korunur).
 * · DOKUNUŞ HER ZAMAN AÇAR/KAPATIR — yetenek hiçbir sezgiye bağlı değildir.
 * · "… Tümünü gör" ipucu YALNIZ kırpılmış olabilecek metinlerde çıkar (bkz. `kirpikOlabilir`);
 *   sezgi yanılsa bile kullanıcı metne dokunarak yine ulaşır.
 * · Açıkken `numberOfLines` KALDIRILIR → metnin tamamı görünür ve seçilebilir kalır.
 *
 * ⚠️ NEDEN AYRI BİR BİLEŞEN: aynı arıza İKİ ayrı yerde bildirildi (bildirim paneli + AI
 * analiz detayları) ve depoda daha çok kırpılan cümle var. Her birine ayrı çözüm yazmak,
 * bir sonrakinde arızayı yeniden doğururdu — bu deponun tekrar eden sınıfı.
 */
import { useState } from "react";
import { StyleProp, StyleSheet, Text, TextStyle, TouchableOpacity } from "react-native";
import { colors, typography } from "@/theme/tokens";
import { kirpikOlabilir } from "@/utils/metinKirpma";

export function GenisletilebilirMetin({
  children,
  satir = 2,
  style,
  testID,
  acEtiketi = "Tümünü gör",
  kapatEtiketi = "Daha az",
}: {
  children: string;
  /** Kapalıyken gösterilecek satır sayısı (eski `numberOfLines` değeri ne ise o). */
  satir?: number;
  style?: StyleProp<TextStyle>;
  testID?: string;
  acEtiketi?: string;
  kapatEtiketi?: string;
}) {
  const [acik, setAcik] = useState(false);
  const ipucuGoster = acik || kirpikOlabilir(children, satir);

  return (
    <TouchableOpacity
      onPress={() => setAcik((a) => !a)}
      accessibilityRole="button"
      accessibilityState={{ expanded: acik }}
      accessibilityHint={acik ? "Metni kısaltmak için dokunun" : "Metnin tamamını görmek için dokunun"}
      activeOpacity={0.7}
      testID={testID}
    >
      {/* ⚠️ `numberOfLines` AÇIKKEN `undefined` OLMALI, 0 DEĞİL: React Native'de 0 da
          "sınırsız" sayılır ama bazı sürümlerde `0` düşerek stilde kalıntı bırakıyor.
          `undefined` tek anlamlı "sınır yok" değeridir. */}
      <Text style={style} numberOfLines={acik ? undefined : satir} selectable testID={testID ? `${testID}-metin` : undefined}>
        {children}
      </Text>
      {ipucuGoster ? (
        <Text style={styles.ipucu} testID={testID ? `${testID}-ipucu` : undefined}>
          {acik ? `▴ ${kapatEtiketi}` : `▾ ${acEtiketi}`}
        </Text>
      ) : null}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  ipucu: {
    color: colors.primary,
    fontSize: typography.small,
    fontWeight: "700",
    marginTop: 2,
  },
});
