/**
 * ADIM 3 — HEDEF SEÇİMİ (araştırma AI Pro): kare üstünde tıklanabilir halkalar + yedek liste.
 *
 * Kedi hattında hedef ORGAN çiplerinden seçilir; fantom/petri'de hedef karede DURUR (2 tümör
 * odağı, 6 kuyu) ve hangisine doz verileceği görsel bir karardır. Halkalar bu kararı ekranda
 * verdirir; `id` KALICI kimliktir (backend `_kimlik_ata`) → seans şeridi ve onay mührü aynı
 * hedeften bahseder.
 *
 * ⚠️ KOORDİNAT: halkalar `pxn` (0..1, kare oranı) ile yerleştirilir, ham `px` ile DEĞİL. WS
 * önizlemesi kareyi 960 px'e küçültüp yayınlar (`imageW` küçültülmüş boyuttur); ham piksel /
 * küçültülmüş genişlik oranı işaretleri hedeften kaydırırdı.
 *
 * ⚠️ YEDEK LİSTE ZORUNLU: halkalar çakışabilir (yan yana kuyular) ve ekran okuyucuyla halka
 * gezinmek zordur. Aynı hedefler ≥44 px satırlarla listelenir; iki yol AYNI `onSec`i çağırır.
 */
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";
import { colors, spacing, typography, touch } from "@/theme/tokens";

/** `/ai/pro/status` ve WS `ai_vision` içindeki hedef adayı (yalnız-ek alanlar). */
export interface HedefAdayi {
  /** KALICI kimlik — `/ai/pro/organ` gövdesindeki `organ_id` budur. */
  id?: number;
  label?: string;
  /** Kare oranına göre merkez [0..1, 0..1]. */
  pxn?: number[];
  x?: number;
  y?: number;
  z?: number;
  /** Modelin SINIFI (kanserli/sağlıklı) — kimlikle karıştırılmamalı. */
  organ_id?: number;
  reliability?: number;
  secili?: boolean;
}

const HALKA = 34;

/** Kare ÜSTÜNE çizilen halkalar — kamera kutusunun içine mutlak konumla yerleştirilir. */
export function HedefHalkalari({
  hedefler,
  seciliId,
  onSec,
  kutu,
  kilitli = false,
}: {
  hedefler: HedefAdayi[];
  seciliId: number;
  onSec: (id: number) => void;
  kutu: { width: number; height: number } | null;
  kilitli?: boolean;
}) {
  if (!kutu || hedefler.length === 0) return null;
  return (
    <View style={styles.katman} pointerEvents="box-none">
      {hedefler.map((h, i) => {
        const pxn = h.pxn;
        if (!pxn || pxn.length < 2) return null;
        const secim = seciliId > 0 ? h.id === seciliId : Boolean(h.secili);
        const guven = Math.round((Number(h.reliability) || 0) * 100);
        return (
          <TouchableOpacity
            key={h.id ?? i}
            testID={`hedef-halka-${h.id ?? i}`}
            style={[
              styles.halka,
              secim && styles.halkaSecili,
              {
                left: Math.round(pxn[0] * kutu.width - HALKA / 2),
                top: Math.round(pxn[1] * kutu.height - HALKA / 2),
              },
            ]}
            onPress={() => onSec(Number(h.id) || 0)}
            disabled={kilitli}
            accessibilityRole="button"
            accessibilityState={{ selected: secim, disabled: kilitli }}
            accessibilityLabel={
              `Hedef ${i + 1} / ${hedefler.length}: ${h.label || "hedef"}, güven yüzde ${guven}` +
              (secim ? ", seçili" : "")
            }
          >
            <Text style={[styles.halkaMetin, secim && styles.halkaMetinSecili]} numberOfLines={1}>
              {secim ? "✓" : String(i + 1)}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

/** Halkaların ZORUNLU yedeği: aynı hedefler dokunulabilir satırlar hâlinde. */
export function HedefListesi({
  hedefler,
  seciliId,
  onSec,
  kilitli = false,
  otomatikMi = true,
}: {
  hedefler: HedefAdayi[];
  seciliId: number;
  onSec: (id: number) => void;
  kilitli?: boolean;
  /** Hiçbir hedef elle seçilmediyse (seciliId 0) etiket "otomatik seçildi" der. */
  otomatikMi?: boolean;
}) {
  if (hedefler.length === 0) return null;
  return (
    <View style={styles.liste}>
      <Text style={styles.label}>🎯 Hedefler (kare üstünden ya da buradan seçin)</Text>
      {hedefler.map((h, i) => {
        const secim = seciliId > 0 ? h.id === seciliId : Boolean(h.secili);
        const guven = Math.round((Number(h.reliability) || 0) * 100);
        const oto = secim && otomatikMi && seciliId === 0;
        return (
          <TouchableOpacity
            key={h.id ?? i}
            testID={`hedef-satir-${h.id ?? i}`}
            style={[styles.satir, secim && styles.satirSecili]}
            onPress={() => onSec(Number(h.id) || 0)}
            disabled={kilitli}
            accessibilityRole="button"
            accessibilityState={{ selected: secim, disabled: kilitli }}
            accessibilityLabel={
              `Hedef ${i + 1} / ${hedefler.length}: ${h.label || "hedef"}, güven yüzde ${guven}` +
              (oto ? ", otomatik seçildi" : secim ? ", seçili" : "")
            }
          >
            <Text style={[styles.satirAd, secim && styles.satirAdSecili]} numberOfLines={1}>
              {secim ? "● " : "○ "}
              {h.label || `Hedef ${i + 1}`}
            </Text>
            <Text style={styles.satirGuven}>{`%${guven}`}</Text>
            {oto ? <Text style={styles.oto}>otomatik seçildi</Text> : null}
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  katman: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  // Dokunma tabanı ölçekle küçülmez (dokunma-hedefi kapısı: touch.min).
  halka: {
    position: "absolute", minHeight: touch.min, minWidth: touch.min,
    width: touch.min, height: touch.min, borderRadius: touch.min,
    borderWidth: 2, borderColor: "rgba(255,255,255,0.85)", backgroundColor: "rgba(15,23,42,0.35)",
    alignItems: "center", justifyContent: "center",
  },
  halkaSecili: { borderColor: colors.primary, borderWidth: 3, backgroundColor: "rgba(79,140,255,0.28)" },
  halkaMetin: { color: "#fff", fontWeight: "800", fontSize: typography.small },
  halkaMetinSecili: { color: colors.white },
  liste: { gap: spacing.xs },
  label: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700" },
  satir: {
    minHeight: touch.min, flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: "#0f172a", borderRadius: 8, paddingHorizontal: spacing.md,
    borderWidth: 1, borderColor: "#1e293b",
  },
  satirSecili: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  satirAd: { color: colors.textMuted, fontSize: typography.small, fontWeight: "700", flex: 1 },
  satirAdSecili: { color: colors.white },
  satirGuven: { color: colors.primary, fontSize: typography.small, fontWeight: "800" },
  oto: { color: colors.textSubtle, fontSize: typography.small, fontStyle: "italic" },
});
