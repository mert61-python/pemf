/**
 * ADIM 1 — HEDEF MODELİ SEÇİMİ (araştırma AI Pro).
 *
 * Sahip isteği: araştırma modunda AI Pro kedi yerine iki modelle çalışır. Kart, seçimden ÖNCE üç
 * soruyu yanıtlar: bu model NE yapar, bu cihazda KURULU mu, şu an DOZ verebilir mi.
 *
 * ⚠️ Kartlar yetki vermez: seçim yalnız isteklerin `model` alanını belirler. Doz onayı ve sürüş
 * backend'de mühür + `PEMF_ARASTIRMA_AIPRO` bayrağıyla kapılıdır (bkz. servers/ai_pro_hedef.py).
 *
 * ⚠️ Bayrak KAPALIYKEN kart PASİF DEĞİL, "yalnız görüntüleme" olarak işaretlenir: hazırlık
 * önizlemesi (kamera + hedef + 3B konum rozeti) bayraktan bağımsız çalışır ve sahibin tezgâh
 * ölçümü (plan kararı #6: hedef düzlemini ölçüp yazmak) tam bu önizlemeyi gerektirir. Öneri/sürüş
 * yolunu backend 409 ile kapatır ve kart bunu peşinen söyler.
 */
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, typography, touch } from "@/theme/tokens";
import { type HedefModeli, MODEL_PROFILLERI } from "@/components/domain/aiProProfilleri";

/** Modelin kurulum durumu — `GET /api/ai/hazirlik` envanterinden türetilir. */
export type KurulumDurumu = "hazir" | "eksik" | "bilinmiyor";

export function ModelSecimKartlari({
  modeller,
  secili,
  onSec,
  kilitli = false,
  kilitNedeni = "",
  kurulum = {},
  arastirmaAcik = null,
}: {
  modeller: HedefModeli[];
  secili: HedefModeli | "";
  onSec: (m: HedefModeli) => void;
  /** Seans/hazırlık sürerken model değiştirilemez. */
  kilitli?: boolean;
  kilitNedeni?: string;
  kurulum?: Partial<Record<HedefModeli, KurulumDurumu>>;
  /** `arastirmaAiProAcik`: null = bilinmiyor (eski sunucu / durum okunamadı). */
  arastirmaAcik?: boolean | null;
}) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>🔬 Hedef Modeli</Text>
      {modeller.map((m) => {
        const p = MODEL_PROFILLERI[m];
        const secim = secili === m;
        const durum = kurulum[m] ?? "bilinmiyor";
        const eksik = durum === "eksik";
        const pasif = kilitli || eksik;
        return (
          <TouchableOpacity
            key={m}
            style={[styles.kart, secim && styles.kartSecili, pasif && styles.kartPasif]}
            onPress={() => onSec(m)}
            disabled={pasif}
            accessibilityRole="button"
            accessibilityLabel={`${p.baslik}: ${p.aciklama}`}
            accessibilityState={{ selected: secim, disabled: pasif }}
          >
            <View style={styles.kartUst}>
              <Text style={styles.simge}>{p.simge}</Text>
              <Text style={[styles.baslik, secim && styles.baslikSecili]} numberOfLines={1}>
                {p.baslik}
              </Text>
              {secim ? <Text style={styles.tik}>✓</Text> : null}
            </View>
            <Text style={styles.aciklama}>{p.aciklama}</Text>
            <View style={styles.rozetler}>
              {durum === "hazir" ? (
                <Text style={[styles.rozet, styles.rozetIyi]}>Model kurulu ✓</Text>
              ) : eksik ? (
                <Text style={[styles.rozet, styles.rozetKotu]}>Araştırma model paketi bu cihazda kurulu değil</Text>
              ) : (
                <Text style={styles.rozet}>Kurulum durumu okunamadı</Text>
              )}
              {arastirmaAcik === false ? (
                <Text style={[styles.rozet, styles.rozetUyari]}>Deneysel — şimdilik yalnız görüntüleme</Text>
              ) : null}
            </View>
          </TouchableOpacity>
        );
      })}
      {kilitli && kilitNedeni ? <Text style={styles.kilit}>{kilitNedeni}</Text> : null}
      {arastirmaAcik === false ? (
        <Text style={styles.note}>
          Bu sürümde fantom/petri hedefine doz ONAYLANAMAZ: 3B konum dönüşümü tezgâhta
          doğrulanmadı. Kamerayı açıp hedefi ve konumu görebilir, yerleşimi ölçebilirsiniz.
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  label: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700" },
  // Dokunma tabanı ölçekle küçülmez (dokunma-hedefi kapısı: touch.min).
  kart: {
    minHeight: touch.min, backgroundColor: "#0f172a", borderRadius: 12, padding: spacing.md,
    borderWidth: 1, borderColor: "#1e293b", gap: spacing.xs,
  },
  kartSecili: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  kartPasif: { opacity: 0.5 },
  kartUst: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  simge: { fontSize: typography.subtitle },
  baslik: { color: colors.text, fontSize: typography.body, fontWeight: "800", flex: 1 },
  baslikSecili: { color: colors.white },
  tik: { color: colors.primary, fontSize: typography.body, fontWeight: "800" },
  aciklama: { color: colors.textMuted, fontSize: typography.small },
  rozetler: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  rozet: {
    color: colors.textSubtle, fontSize: typography.small, fontWeight: "700",
    backgroundColor: "#1e293b", borderRadius: 6, paddingHorizontal: spacing.sm, paddingVertical: 2,
  },
  rozetIyi: { color: "#bbf7d0", backgroundColor: colors.successSoft },
  rozetKotu: { color: "#fecaca", backgroundColor: colors.dangerSoft },
  rozetUyari: { color: "#fde68a", backgroundColor: colors.warningSoft },
  kilit: { color: colors.warning, fontSize: typography.small, fontWeight: "700" },
  note: { color: colors.textMuted, fontSize: typography.small, fontStyle: "italic" },
});
