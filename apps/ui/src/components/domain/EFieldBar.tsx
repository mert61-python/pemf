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
 *   * 5 sn'den uzun süredir YENİ hesap ALINMADIYSA "duraklandı" rozeti çıkar (bar donmuş sayıyı canlı sanmasın).
 *     Yaş, verinin bu istemciye ALINIŞ zamanından ölçülür (D6.25) — sunucu damgası yerel saatle karşılaştırılmaz.
 *   * `activeCoils === 0` iken değerler sıfırdır ve bunu açıkça yazar.
 */
import { useEffect, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { Zap } from "lucide-react-native";

import { useLiveData } from "@/context/LiveDataContext";
import { colors, rf, rs, spacing } from "@/theme/tokens";
import type { EFieldLive } from "@/types/domain";
import { useTranslation } from "react-i18next";

export function EFieldBar() {
  const { t } = useTranslation();
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
    const zamanlayici = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(zamanlayici);
  }, []);
  // ⚠️ D6.25 (B-6.16): yaş = son YENİ hesabın bu istemciye ALINIŞINDAN beri geçen süre (yerel saat). Eskiden `now / 1000 - e.ts`
  // sunucu damgasını (efield_live `time.time()`) istemci saatiyle karşılaştırıyordu: saat kayınca (ayrı makinedeki LAN istemcisi)
  // sunucu GERİDE → az önce gelen veri "duraklandı", İLERİDE → donmuş veri süresiz "canlı". Yeni hesap = damga DEĞİŞTİ (damgasız
  // eski backend'de nesne değişti); aynı damgalı yeniden yayın (başka bir olayla gelen tam snapshot) veriyi TAZELEMEZ.
  const anahtar: unknown = e ? (Number.isFinite(e.ts) && e.ts > 0 ? e.ts : e) : null;
  const sonAnahtarRef = useRef<unknown>(null);
  const alinisRef = useRef(0);
  if (anahtar !== null && anahtar !== sonAnahtarRef.current) {
    sonAnahtarRef.current = anahtar;
    alinisRef.current = Date.now();
  }

  if (!e) return null; // ← bağlam/seans yok: bar HİÇ çıkmaz

  const stale = now - alinisRef.current > 5000;
  const peak = peakRef.current || 1;
  const pct = (v: number | null) => (v === null ? 0 : Math.max(0, Math.min(100, (v / peak) * 100)));
  // ODK10: kuyu sıvısı içindeki E mV/m düzeyinde → 0,001'in altında 3 anlamlı basamak ("0.0000" yuvarlaması "sıfır" diye okunurdu).
  const fmt = (v: number | null) => (v === null ? "—" : v >= 1 ? v.toFixed(3) : v >= 0.001 || v === 0 ? v.toFixed(4) : v.toPrecision(3));
  const bMetni = Number.isFinite(e.achievedB_T) ? ((e.achievedB_T as number) * 1000).toFixed(2) : "—";
  const dutyMetni = Number.isFinite(e.dutySum) ? e.dutySum.toFixed(2) : "—";
  const neden = e.egitimAraligiDisi
    ? t("kontrol.efield.egitimDisi")
    : e.bOlculmuyor
      ? t("kontrol.efield.bOlculmuyor")
      : e.egitimAraligiBilinmiyor
        ? t("kontrol.efield.egitimBilinmiyor")
        : null;

  return (
    <View style={styles.card} accessibilityLabel={t("kontrol.efield.etiket")}>
      <View style={styles.head}>
        <Zap size={rs(16)} color={colors.warning} />
        <Text style={styles.title}>{t("kontrol.efield.baslik")}</Text>
        <Text style={stale ? styles.stale : styles.live}>{stale ? t("kontrol.efield.duraklandi") : t("kontrol.efield.canli")}</Text>
      </View>
      {/* ODK6 (istem 45): ODAK seansında E = sürülen planın E'si (hesaplanan; E ölçülmedi). ODK10: petri → kuyu SIVISI içinde; diğer → havada.
          Analiz bağlamında vekil model → "yaklaşık". */}
      {e.kaynak === "cst" && e.ortam === "kuyu" ? (
        <Text testID="efield-cst-kuyu" style={styles.foot}>{t("kontrol.efield.cstKuyu")}</Text>
      ) : e.kaynak === "cst" ? (
        <Text testID="efield-cst" style={styles.foot}>{t("kontrol.efield.cst")}</Text>
      ) : (
        <Text testID="efield-yaklasik" style={styles.foot}>{t("kontrol.efield.yaklasik")}</Text>
      )}

      {/* AP-15: petri ODAK (ortam "kuyu") E'si HEDEF kuyu ve ÇEVRE kuyulardır — "Tümör / Sağlıklı" yanıltıcıydı. */}
      <Row
        label={e.ortam === "kuyu" ? t("kontrol.efield.hedefKuyu") : t("kontrol.efield.tumor")}
        value={cancer}
        pct={pct(cancer)}
        tint={colors.danger}
        fmt={fmt}
      />
      <Row
        label={e.ortam === "kuyu" ? t("kontrol.efield.cevreKuyular") : t("kontrol.efield.saglikli")}
        value={healthy}
        pct={pct(healthy)}
        tint={colors.success}
        fmt={fmt}
      />

      <Text style={styles.foot}>
        {t("kontrol.efield.ozet", { count: e.activeCoils, b: bMetni, duty: dutyMetni })}
      </Text>
      {/* Y51 (sahip): Σduty modelin eğitim aralığı dışında → değer GÖSTERİLİR, yanında güvenilmezlik etiketi. */}
      {e.dutyEgitimAraligiDisi ? (
        <Text style={styles.uyari} testID="efield-duty-araligi-disi" accessibilityRole="text">
          {e.dutyEgitimAraligi ? t("kontrol.efield.dutyDisiAralikli", { min: e.dutyEgitimAraligi[0].toFixed(2), max: e.dutyEgitimAraligi[1].toFixed(2) }) : t("kontrol.efield.dutyDisi")}
        </Text>
      ) : null}
      {neden ? <Text style={styles.foot}>{neden}</Text> : null}
      {e.activeCoils === 0 && (
        <Text style={styles.foot}>{t("kontrol.efield.bobinlerDurdu")}</Text>
      )}
    </View>
  );
}

function Row({ label, value, pct, tint, fmt }: {
  label: string; value: number | null; pct: number; tint: string; fmt: (v: number | null) => string;
}) {
  const { t } = useTranslation();
  return (
    <View style={styles.row} accessibilityLabel={t("kontrol.efield.satirEtiketi", { label, deger: fmt(value) })}>
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
  uyari: { color: colors.warning, fontSize: rf(11), fontWeight: "700" },
});
