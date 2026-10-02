// Author: mertaygn, cglrgrkn
/**
 * CANLI E-ALANI BARI (2026-08-06)
 *
 * Tedavi sürerken elektrik alanını gerçek zamanlı gösterir. Değerler backend'de 2 Hz'de
 * eğitilmiş vekil modelden üretilir (`servers/efield_live.py`) — AI analiz panelindeki
 * `E_cancer`/`E_healthy` ile AYNI model, dolayısıyla iki ekran birbirini tutar (uydurma
 * katsayıyla türetilmiş ikinci bir sayı YOK).
 *
 * GÖSTERİLMEME KURALLARI (kasıtlı — yanlış güvence vermemek için):
 *   * `eField` yoksa (analiz yapılmamış / seans pasif) bileşen HİÇ render olmaz.
 *     Uydurma ya da bayat bir değeri "canlı" diye göstermek operatörü yanıltır.
 *   * Veri ≥5 sn eskiyse "duraklandı" rozeti çıkar (bar donmuş sayıyı canlı sanmasın).
 *   * `activeCoils === 0` iken değerler sıfırdır ve bunu açıkça yazar.
 */
import { useEffect, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { Zap } from "lucide-react-native";

import { useLiveData } from "@/context/LiveDataContext";
import { colors, rf, rs, spacing } from "@/theme/tokens";
import type { EFieldLive } from "@/types/domain";

export function EFieldBar() {
  const { snapshot } = useLiveData();
  const e = (snapshot as { eField?: EFieldLive | null } | null)?.eField ?? null;

  // Ölçek: sabit tavan YOK (model çıktısının aralığı kuruluma göre değişir) → görülen en
  // yüksek değeri tavan tut. Yalnız BÜYÜR; küçülürse bar her tikte zıplar ve okunamaz olur.
  const peakRef = useRef(0);
  const [, force] = useState(0);
  // ⚠️ D1.76 · İG-5.83 · Y6: sayı OLMAYAN değer (backend E'yi hesaplamadı: B eğitim aralığı dışında / alan
  // ölçülmüyor) `null` kalır ve '—' çizilir. Eskiden 0'a çevrilip "0.0000" yazılıyordu — "ölçüldü, sıfır" okunur.
  const cancer = Number.isFinite(e?.cancer) ? (e as EFieldLive).cancer as number : null;
  const healthy = Number.isFinite(e?.healthy) ? (e as EFieldLive).healthy as number : null;
  useEffect(() => {
    const m = Math.max(cancer ?? 0, healthy ?? 0);
    if (m > peakRef.current * 1.02) {
      peakRef.current = m;
      force((n) => n + 1);
    }
  }, [cancer, healthy]);

  // Tazelik: backend 2 Hz yazar; 5 sn susmuşsa hesap durmuştur.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  if (!e) return null; // ← bağlam/seans yok: bar HİÇ çıkmaz

  const stale = e.ts > 0 && now / 1000 - e.ts > 5;
  const peak = peakRef.current || 1;
  const pct = (v: number | null) => (v === null ? 0 : Math.max(0, Math.min(100, (v / peak) * 100)));
  const fmt = (v: number | null) => (v === null ? "—" : v >= 1 ? v.toFixed(3) : v.toFixed(4));
  const bMetni = Number.isFinite(e.achievedB_T) ? ((e.achievedB_T as number) * 1000).toFixed(2) : "—";
  const dutyMetni = Number.isFinite(e.dutySum) ? e.dutySum.toFixed(2) : "—";
  const neden = e.egitimAraligiDisi
    ? "Ölçülen B, modelin eğitim aralığı dışında — E hesaplanmadı (model orada güvenilir değil)."
    : e.bOlculmuyor
      ? "Çalışan bobinlerde alan (B) ölçülmüyor — E hesaplanmadı."
      : e.egitimAraligiBilinmiyor
        ? "Modelin eğitim aralığı okunamadı — E hesaplanmadı."
        : null;

  return (
    <View style={styles.card} accessibilityLabel="Canlı elektrik alanı göstergesi">
      <View style={styles.head}>
        <Zap size={rs(16)} color={colors.warning} />
        <Text style={styles.title}>Canlı E-Alanı</Text>
        <Text style={stale ? styles.stale : styles.live}>{stale ? "duraklandı" : "● canlı"}</Text>
      </View>

      <Row label="Tümör" value={cancer} pct={pct(cancer)} tint={colors.danger} fmt={fmt} />
      <Row label="Sağlıklı" value={healthy} pct={pct(healthy)} tint={colors.success} fmt={fmt} />

      <Text style={styles.foot}>
        {e.activeCoils} bobin · B={bMetni} mT · Σduty={dutyMetni}
      </Text>
      {neden ? <Text style={styles.foot}>{neden}</Text> : null}
      {e.activeCoils === 0 && (
        <Text style={styles.foot}>Bobinler durdu — alan üretilmiyor.</Text>
      )}
    </View>
  );
}

function Row({ label, value, pct, tint, fmt }: {
  label: string; value: number | null; pct: number; tint: string; fmt: (v: number | null) => string;
}) {
  return (
    <View style={styles.row} accessibilityLabel={`${label} alan ${fmt(value)}`}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${pct}%`, backgroundColor: tint }]} />
      </View>
      <Text style={[styles.value, { color: tint }]}>{fmt(value)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.panel,
    borderRadius: rs(14),
    padding: rs(14),
    gap: rs(8),
    borderWidth: 1,
    borderColor: colors.border,
  },
  head: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  title: { flex: 1, color: colors.text, fontSize: rf(14), fontWeight: "700" },
  live: { color: colors.success, fontSize: rf(11), fontWeight: "700" },
  stale: { color: colors.textMuted, fontSize: rf(11), fontWeight: "700" },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  label: { width: rs(64), color: colors.textMuted, fontSize: rf(12) },
  track: {
    flex: 1,
    height: rs(10),
    borderRadius: rs(5),
    backgroundColor: colors.bg,
    overflow: "hidden",
  },
  fill: { height: "100%", borderRadius: rs(5) },
  value: { width: rs(66), textAlign: "right", fontSize: rf(12), fontWeight: "700" },
  foot: { color: colors.textMuted, fontSize: rf(11) },
});
