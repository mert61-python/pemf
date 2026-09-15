// Author: mertaygn
/**
 * TAKİP GRAFİĞİ — aynı hayvanın analizleri zaman içinde (sahip isteği 2026-09-12, öneri #4).
 * ========================================================================================
 * Ev sahibi "Mia'nın durumu iyiye mi gidiyor?" sorusunu tek bakışta görsün.
 *
 * ⚠️ ÇİZİM SVG DEĞİL, DÜZ `View`LARLA: bu ekranda zaten bir grafik kütüphanesi yok ve
 * yalnız bir mini-eğilim için `react-native-chart-kit` çekmek (SVG + bağımlılık) bu kartın
 * hak ettiğinden fazlası olurdu. Çubuklar `flex` ile oranlanır — RNW'de de birebir çalışır.
 *
 * ⚠️ SERİ KURALLARI `utils/takipSerisi.ts`TE: tek modül · tek ölçüt · en az iki nokta.
 * Bu bileşen yalnız ÇİZER; "ne çizilir" kararı saf ve test edilebilir yerdedir.
 */
import { StyleSheet, Text, View } from "react-native";
import { Card } from "@/components/ui/Card";
import { colors, radius, rs, spacing, typography } from "@/theme/tokens";
import type { TakipSerisi } from "@/utils/takipSerisi";

export function TakipGrafigi({ seri, hasta, testID = "takip-grafigi" }: {
  seri: TakipSerisi;
  hasta: string;
  testID?: string;
}) {
  const degerler = seri.noktalar.map((n) => n.deger);
  const enBuyuk = Math.max(...degerler);
  const enKucuk = Math.min(...degerler);
  // ⚠️ TABAN SIFIR (negatif yoksa): eksen en küçük değerden başlarsa 41 ile 42 arasındaki
  // fark DAĞ gibi görünür ve ev sahibi olmayan bir iyileşme/kötüleşme okur.
  const taban = Math.min(0, enKucuk);
  const aralik = Math.max(1, enBuyuk - taban);

  const ilk = seri.noktalar[0].deger;
  const son = seri.noktalar[seri.noktalar.length - 1].deger;
  const fark = son - ilk;

  return (
    <Card style={styles.kart}>
      <View style={styles.baslikSatiri} testID={testID}>
        <Text style={styles.baslik} numberOfLines={1}>
          📈 {hasta} · {seri.baslik} değişimi
        </Text>
        <Text style={[styles.fark, fark === 0 ? styles.farkNotr : fark > 0 ? styles.farkArti : styles.farkEksi]}>
          {fark > 0 ? "▲" : fark < 0 ? "▼" : "■"} {Math.abs(fark)}
          {seri.birim}
        </Text>
      </View>

      <View style={styles.grafik} testID={`${testID}-cubuklar`}>
        {seri.noktalar.map((n, i) => (
          <View key={`${n.t}-${i}`} style={styles.sutun}>
            <Text style={styles.deger} numberOfLines={1}>
              {n.deger}
              {seri.birim}
            </Text>
            <View style={styles.cubukYuvasi}>
              {/* Yükseklik ORANLA verilir: kap yüksekliği bilinmeden de doğru çalışır. */}
              <View style={[styles.cubuk, { flex: Math.max(0.04, (n.deger - taban) / aralik) }]} />
              <View style={{ flex: Math.max(0, 1 - (n.deger - taban) / aralik) }} />
            </View>
            <Text style={styles.tarih} numberOfLines={1}>{n.etiket}</Text>
          </View>
        ))}
      </View>

      {/* ⚠️ DIŞARIDA KALANLAR SESSİZ BIRAKILMAZ: karışık modüllü geçmişte kullanıcı
          "neden 3 analiz var ama grafikte 2 nokta?" diye sormamalı. */}
      {seri.disaridaKalan > 0 ? (
        <Text style={styles.not} testID={`${testID}-disarida`}>
          {`Yalnız aynı tür analizler karşılaştırılır — ${seri.disaridaKalan} farklı analiz grafiğe alınmadı.`}
        </Text>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  kart: { gap: spacing.sm, marginHorizontal: spacing.lg, marginBottom: spacing.md },
  baslikSatiri: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: spacing.xs },
  baslik: { color: colors.text, fontSize: typography.body, fontWeight: "800", flexShrink: 1 },
  fark: { fontSize: typography.small, fontWeight: "800" },
  farkArti: { color: colors.success },
  farkEksi: { color: colors.warning },
  farkNotr: { color: colors.textMuted },
  grafik: { flexDirection: "row", alignItems: "flex-end", gap: rs(6), height: rs(140) },
  sutun: { flex: 1, alignItems: "center", height: "100%" },
  deger: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700" },
  cubukYuvasi: { flex: 1, width: "100%", flexDirection: "column-reverse", minWidth: rs(10) },
  cubuk: { backgroundColor: colors.primary, borderTopLeftRadius: radius.sm, borderTopRightRadius: radius.sm },
  tarih: { color: colors.textMuted, fontSize: typography.small, marginTop: 2 },
  not: { color: colors.textMuted, fontSize: typography.small },
});
