// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) A3 — Kontrol sekmesi "Alan haritası" kartı: çalışan bobinlerin duty / faz / frekansından sunucunun hesapladığı tepe |B|
 * dağılımının YATAY KESİTİ (üstten bakış, ön aşağıda), saniyede bir.
 * =====================================================================================================================================
 * - Varsayılan KAPALI; açılınca abone olur (`useAlanHaritasi`), kapanınca / ekrandan çıkınca abonelik biter (sunucu hesabı durur).
 * - Katman: taban (plaka yüksekliği, varsayılan) · orta · tavan. Renk ölçeği BÜTÜN hacmin en yükseğine göre (katmanlar karşılaştırılabilir).
 * - Dokunuş / tıklamayla nokta değeri; en yüksek değer + yeri; "Model tahmini, ölçüm değil" etiketi HER ZAMAN görünür.
 * - Sensör (MLX) ölçümü varsa değeri yazılır — sensörün kabindeki yeri üründe tanımlı OLMADIĞI için haritaya işlenmez.
 * - YALNIZ GÖSTERİM: hiçbir sürüş kararı bu karttan alınmaz; ACİL DURDUR ve kontrol akışı bu karttan ETKİLENMEZ (kart sekme içeriğinin
 *   ALTINDA durur, ACİL DURDUR düğmesinin yeri değişmez).
 */
import { useMemo, useState } from "react";
import { StyleSheet, Switch, Text, TouchableOpacity, View, type LayoutChangeEvent } from "react-native";
import Svg, { Rect } from "react-native-svg";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import { useLiveData } from "@/context/LiveDataContext";
import { useAlanHaritasi } from "@/hooks/useAlanHaritasi";
import {
  KATMANLAR,
  haritayiCoz,
  katmanIndeksi,
  kesit,
  kesitEnBuyuk,
  mTBicimle,
  renk,
  type AlanHaritasiVerisi,
  type Katman,
  type KesitHucresi,
} from "@/services/alanHaritasi";
import { alanGosterilebilir } from "@/utils/olculenAlan";
import { stmBobiniMi } from "@/services/bobinGorunurlugu";
import { colors, rf, rs, spacing, touch } from "@/theme/tokens";

function durumMetni(t: TFunction, durum: string): string {
  switch (durum) {
    case "sifir":
      return t("kontrol.alanHaritasi.durum.sifir");
    case "kalibrasyonYok":
      return t("kontrol.alanHaritasi.durum.kalibrasyonYok");
    case "kalibrasyonBozuk":
      return t("kontrol.alanHaritasi.durum.kalibrasyonBozuk");
    case "kalibrasyonEski":
      return t("kontrol.alanHaritasi.durum.kalibrasyonEski");
    case "eslemeDogrulanmadi":
      return t("kontrol.alanHaritasi.durum.eslemeDogrulanmadi");
    case "modelYok":
      return t("kontrol.alanHaritasi.durum.modelYok");
    case "modelBozuk":
      return t("kontrol.alanHaritasi.durum.modelBozuk");
    default:
      return t("kontrol.alanHaritasi.durum.hata");
  }
}

function katmanEtiketi(t: TFunction, k: Katman): string {
  if (k === "taban") return t("kontrol.alanHaritasi.katman.taban");
  if (k === "orta") return t("kontrol.alanHaritasi.katman.orta");
  return t("kontrol.alanHaritasi.katman.tavan");
}

function uyariMetni(t: TFunction, u: string): string | null {
  if (u === "dutyKirpildi") return t("kontrol.alanHaritasi.uyari.dutyKirpildi");
  if (u === "frekansKalibrasyonDisi") return t("kontrol.alanHaritasi.uyari.frekansKalibrasyonDisi");
  return null;
}

/** Sensör (MLX) son ölçümü: ölçülen alanı bildiren STM bobinlerinin en büyüğü (doğrulanamayan kazanç hariç); yoksa null. */
export function sensorOlcumu(coils: unknown): number | null {
  let m: number | null = null;
  for (const c of Array.isArray(coils) ? coils : []) {
    const k = c as { id?: number; magneticMt?: number; measuredFields?: string[]; alanDogrulanamadi?: boolean };
    if (!stmBobiniMi(Number(k?.id))) continue; // bobin sayısı TEK KAYNAK (D5.42)
    if (k.alanDogrulanamadi || !Array.isArray(k.measuredFields) || !alanGosterilebilir(k, "magneticMt")) continue;
    const v = Number(k.magneticMt);
    if (Number.isFinite(v) && (m === null || v > m)) m = v;
  }
  return m;
}

export function AlanHaritasiKarti() {
  const { t } = useTranslation();
  const [acik, setAcik] = useState(false);
  const veri = useAlanHaritasi(acik);
  const { snapshot } = useLiveData();
  const mlx = sensorOlcumu((snapshot as { coils?: unknown } | null)?.coils);
  return (
    <View style={styles.card} testID="alan-haritasi-karti">
      <View style={styles.head}>
        <Text style={styles.title}>{t("kontrol.alanHaritasi.baslik")}</Text>
        <Switch
          value={acik}
          onValueChange={setAcik}
          testID="alan-haritasi-ac"
          accessibilityLabel={t("kontrol.alanHaritasi.acKapat")}
        />
      </View>
      {!acik ? (
        <Text style={styles.foot}>{t("kontrol.alanHaritasi.kapali")}</Text>
      ) : (
        <>
          <Text style={styles.model} testID="alan-haritasi-model-tahmini">
            {t("kontrol.alanHaritasi.modelTahmini")}
          </Text>
          <Govde veri={veri} />
          {mlx !== null && (
            <Text style={styles.foot} testID="alan-haritasi-mlx">
              {t("kontrol.alanHaritasi.mlx", { deger: mTBicimle(mlx) })}
            </Text>
          )}
        </>
      )}
    </View>
  );
}

function Govde({ veri }: { veri: AlanHaritasiVerisi | null }) {
  const { t } = useTranslation();
  const [katman, setKatman] = useState<Katman>("taban");
  const [secili, setSecili] = useState<{ satir: number; sutun: number } | null>(null);
  const [genislik, setGenislik] = useState(0);
  const harita = useMemo(() => haritayiCoz(veri), [veri]);
  const iy = harita ? katmanIndeksi(harita, katman) : 0;
  const satirlar = useMemo(() => (harita ? kesit(harita, iy) : []), [harita, iy]);

  if (!veri) return <Text style={styles.foot}>{t("kontrol.alanHaritasi.bekleniyor")}</Text>;
  if (!harita) {
    return (
      <Text style={veri.durum === "sifir" ? styles.foot : styles.uyari} testID="alan-haritasi-durum">
        {durumMetni(t, veri.durum === "tamam" ? "hata" : String(veri.durum))}
      </Text>
    );
  }
  const tavan = Math.max(veri.enYuksek?.mT ?? 0, kesitEnBuyuk(satirlar));
  const nx = harita.boyut[0];
  const nz = harita.boyut[2];
  const hucre = genislik > 0 ? genislik / nx : 0;
  const tabanY = Array.isArray(veri.izgara?.camIc) ? -Number(veri.izgara?.camIc?.[1]) / 2 : NaN;
  const kesitY = harita.kok[1] + iy * harita.adim;
  const sec: KesitHucresi | null = secili ? satirlar[secili.satir]?.[secili.sutun] ?? null : null;
  const en = veri.enYuksek;
  return (
    <View style={styles.govde}>
      <View style={styles.katmanlar}>
        {KATMANLAR.map((k) => (
          <TouchableOpacity
            key={k}
            style={[styles.chip, katman === k && styles.chipAktif]}
            onPress={() => {
              setKatman(k);
              setSecili(null);
            }}
            accessibilityRole="button"
            accessibilityState={{ selected: katman === k }}
            testID={`alan-katman-${k}`}
          >
            <Text style={[styles.chipText, katman === k && styles.chipTextAktif]}>{katmanEtiketi(t, k)}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {Number.isFinite(tabanY) && (
        <Text style={styles.foot} testID="alan-haritasi-kesit">
          {t("kontrol.alanHaritasi.kesitYuksekligi", { mm: Math.round(kesitY - tabanY) })}
        </Text>
      )}
      <Text style={styles.yon}>{t("kontrol.alanHaritasi.yon.arka")}</Text>
      <View style={styles.haritaSatir}>
        <Text style={styles.yonYan}>{t("kontrol.alanHaritasi.yon.sol")}</Text>
        <View
          style={styles.haritaKutu}
          onLayout={(e: LayoutChangeEvent) => setGenislik(e.nativeEvent.layout.width)}
          testID="alan-haritasi-svg-kutu"
        >
          {hucre > 0 && (
            <Svg width={genislik} height={hucre * nz} testID="alan-haritasi-svg">
              {satirlar.map((s) =>
                s.map((h) => (
                  <Rect
                    key={`${h.satir}-${h.sutun}`}
                    x={h.sutun * hucre}
                    y={h.satir * hucre}
                    width={hucre}
                    height={hucre}
                    fill={h.mT === null ? colors.bg : renk(tavan > 0 ? h.mT / tavan : 0)}
                    stroke={secili && secili.satir === h.satir && secili.sutun === h.sutun ? colors.white : undefined}
                    strokeWidth={secili && secili.satir === h.satir && secili.sutun === h.sutun ? 2 : 0}
                    onPress={() => setSecili({ satir: h.satir, sutun: h.sutun })}
                    testID={`alan-hucre-${h.satir}-${h.sutun}`}
                  />
                )),
              )}
            </Svg>
          )}
        </View>
        <Text style={styles.yonYan}>{t("kontrol.alanHaritasi.yon.sag")}</Text>
      </View>
      <Text style={styles.yon}>{t("kontrol.alanHaritasi.yon.on")}</Text>
      <View style={styles.olcek}>
        <Text style={styles.olcekMetin}>{mTBicimle(0)}</Text>
        <View style={styles.olcekCubuk}>
          {[0, 0.2, 0.4, 0.6, 0.8, 1].map((o) => (
            <View key={o} style={[styles.olcekParca, { backgroundColor: renk(o) }]} />
          ))}
        </View>
        <Text style={styles.olcekMetin} testID="alan-haritasi-olcek-ust">
          {t("kontrol.alanHaritasi.olcekUst", { deger: mTBicimle(tavan) })}
        </Text>
      </View>
      {en && (
        <Text style={styles.deger} testID="alan-haritasi-en-yuksek">
          {t("kontrol.alanHaritasi.enYuksek", {
            deger: mTBicimle(en.mT),
            x: Math.round(en.konum[0]),
            y: Math.round(en.konum[1]),
            z: Math.round(en.konum[2]),
          })}
        </Text>
      )}
      <Text style={styles.foot} testID="alan-haritasi-katman-en-yuksek">
        {t("kontrol.alanHaritasi.katmanEnYuksek", { deger: mTBicimle(kesitEnBuyuk(satirlar)) })}
      </Text>
      <Text style={styles.deger} testID="alan-haritasi-nokta">
        {sec === null
          ? t("kontrol.alanHaritasi.noktaIpucu")
          : sec.mT === null
            ? t("kontrol.alanHaritasi.noktaYok", { x: Math.round(sec.x), z: Math.round(sec.z) })
            : t("kontrol.alanHaritasi.nokta", { x: Math.round(sec.x), z: Math.round(sec.z), deger: mTBicimle(sec.mT) })}
      </Text>
      {(veri.uyarilar ?? []).map((u) => {
        const m = uyariMetni(t, u);
        return m === null ? null : (
          <Text key={u} style={styles.uyari} testID={`alan-haritasi-uyari-${u}`}>
            {m}
          </Text>
        );
      })}
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
    marginTop: spacing.md,
  },
  head: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  title: { flex: 1, color: colors.text, fontSize: rf(14), fontWeight: "700" },
  model: { color: colors.warning, fontSize: rf(12), fontWeight: "700" },
  govde: { gap: rs(6) },
  katmanlar: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    minHeight: touch.sm,
    justifyContent: "center",
    paddingHorizontal: rs(10),
    paddingVertical: rs(6),
    borderRadius: rs(12),
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipAktif: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  chipText: { color: colors.textMuted, fontSize: rf(12) },
  chipTextAktif: { color: colors.text, fontWeight: "700" },
  yon: { color: colors.textSubtle, fontSize: rf(11), textAlign: "center" },
  haritaSatir: { flexDirection: "row", alignItems: "center", gap: rs(4) },
  yonYan: { color: colors.textSubtle, fontSize: rf(11), width: rs(28), textAlign: "center" },
  haritaKutu: { flex: 1 },
  olcek: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  olcekCubuk: { flex: 1, flexDirection: "row", height: rs(10), borderRadius: rs(5), overflow: "hidden" },
  olcekParca: { flex: 1 },
  olcekMetin: { color: colors.textMuted, fontSize: rf(11) },
  deger: { color: colors.text, fontSize: rf(12), fontWeight: "600" },
  foot: { color: colors.textMuted, fontSize: rf(11) },
  uyari: { color: colors.warning, fontSize: rf(11), fontWeight: "700" },
});
