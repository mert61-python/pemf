// Author: mertaygn, cglrgrkn
/**
 * KABİN SENSÖRÜ (MLX) KARTI — Y306 (sahip 19-11, madde 6): tek MLX alan sensörü kabinde GEZDİRİLİYOR; değer bir bobinin değil KABİNİN
 * sensörüdür. Ana Ekran, Kontrol ve Sensörler'de AYNI bileşen, bobin kartlarından AYRI. Değer yalnız kanal gerçekten ÖLÇÜYORSA
 * (`measuredFields`, Y6 / D1.67) ve kazanç ayarı doğrulandıysa (TD2) gösterilir; yoksa "—" (0 UYDURULMAZ). Masaüstü + telefon aynı.
 * Y308 (madde 7): seans SÜRERKEN "Sensör konumu" — İSTEĞE BAĞLI konum girişi (konumlu / serbest, zaman damgalı; sensör taşındıkça
 * yeni giriş). Hiç giriş yapılmazsa hiçbir şey değişmez. Hiçbir sürüş / ACİL DURDUR koşulu buradan geçmez — yalnız gösterim + kayıt.
 */
import { useCallback, useEffect, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Magnet } from "lucide-react-native";
import { useLiveData } from "@/context/LiveDataContext";
import { colors, rf, rs, spacing, touch } from "@/theme/tokens";
import { ondalikMetni } from "@/i18n/dil";
import { alanGosterilebilir } from "@/utils/olculenAlan";
import { KABIN_SENSORU_KANALI } from "@/utils/kabinSensoru";
import { canliKonum, canliKonumEkle, type HazirNokta, type SensorKonumuKaydi } from "@/services/sensorKonumu";
import { SensorKonumuFormu } from "@/components/domain/SensorKonumuFormu";
import type { CoilStatus } from "@/types/domain";

/** Kabin sensörü kanalının canlı alanı (mT) — ölçülmüyorsa / doğrulanamadıysa null. */
export function kabinSensoruAlani(coils: CoilStatus[] | null | undefined): number | null {
  const k = (coils ?? []).find((c) => Number(c?.id) === KABIN_SENSORU_KANALI);
  if (!k || (k as { alanDogrulanamadi?: boolean }).alanDogrulanamadi) return null;
  if (!alanGosterilebilir(k, "magneticMt")) return null;
  const v = Number((k as { magneticMt?: unknown }).magneticMt);
  return Number.isFinite(v) ? v : null;
}

/** Konum girişinin kısa metni (dile göre ondalık). */
export function konumOzeti(t: TFunction, k: SensorKonumuKaydi | null): string {
  if (!k || k.serbest || k.sol_cm === null || k.on_cm === null || k.yukseklik_cm === null) {
    return t("kontrol.kabinSensoru.konum.serbestDurum");
  }
  // YS2 d (B7, YG0 25-11): en çok 2 ondalık, sondaki sıfırlar atılır (0,75 → "0,75"; eskiden "0,8") — PDF / CSV ile AYNI
  // (`servers/sensor_konumu.cm_metni`).
  const s = (v: number) => ondalikMetni(v, 2).replace(/([.,]\d*?)0+$/, "$1").replace(/[.,]$/, "");
  return t("kontrol.kabinSensoru.konum.simdiki", { sol: s(k.sol_cm), on: s(k.on_cm), yukseklik: s(k.yukseklik_cm) });
}

export function KabinSensoruKarti({ testID = "kabin-sensoru-karti" }: { testID?: string }) {
  const { t } = useTranslation();
  const { snapshot } = useLiveData();
  const k = (snapshot?.coils ?? []).find((c) => Number(c?.id) === KABIN_SENSORU_KANALI);
  const deger = kabinSensoruAlani(snapshot?.coils);
  const dogrulanamadi = Boolean((k as { alanDogrulanamadi?: boolean } | undefined)?.alanDogrulanamadi);
  // Y308: konum girişi yalnız seans sürerken (kayıt seansa bağlı); seans yoksa düğme çizilmez.
  const seansVar = (snapshot as { activeTreatment?: { isActive?: boolean } } | null)?.activeTreatment?.isActive === true;
  const [konum, setKonum] = useState<SensorKonumuKaydi | null>(null);
  const [formAcik, setFormAcik] = useState(false);
  // FK K1 d2: tezgâh MLX planının hazır noktaları (veri kökü) — formda tek dokunuşla konum.
  const [hazir, setHazir] = useState<HazirNokta[]>([]);

  const yenile = useCallback(async () => {
    const r = await canliKonum();
    setKonum(r?.aktif ? r.konum : null);
    setHazir(Array.isArray(r?.hazir) ? r.hazir : []);
  }, []);

  useEffect(() => {
    if (!seansVar) {
      setKonum(null);
      setFormAcik(false);
      return;
    }
    yenile();
  }, [seansVar, yenile]);

  return (
    <View style={styles.kart} testID={testID} accessibilityLabel={t("kontrol.kabinSensoru.baslik")}>
      <View style={styles.baslikSatiri}>
        <Magnet size={rs(16)} color={colors.cyan} />
        <Text style={styles.baslik}>{t("kontrol.kabinSensoru.baslik")}</Text>
        <Text style={styles.deger} testID="kabin-sensoru-deger">
          {deger === null ? "—" : `${ondalikMetni(deger, 2)} mT`}
        </Text>
      </View>
      {dogrulanamadi ? <Text style={styles.uyari}>{t("kontrol.bobin.sensorDogrulanamadi")}</Text> : null}
      <Text style={styles.aciklama}>{t("kontrol.kabinSensoru.aciklama")}</Text>
      {seansVar ? (
        <>
          <View style={styles.konumSatiri}>
            <Text style={styles.konum} testID="kabin-sensoru-konum">
              {konumOzeti(t, konum)}
            </Text>
            {!formAcik ? (
              <TouchableOpacity
                style={styles.dugme}
                onPress={() => setFormAcik(true)}
                accessibilityRole="button"
                testID="kabin-sensoru-konum-dugmesi"
              >
                <Text style={styles.dugmeMetni}>{t("kontrol.kabinSensoru.konum.dugme")}</Text>
              </TouchableOpacity>
            ) : null}
          </View>
          {formAcik ? (
            <SensorKonumuFormu
              hazir={hazir}
              tasindi={konum !== null}
              onVazgec={() => setFormAcik(false)}
              onKaydet={async (govde) => {
                let hata: string | null = null;
                const tamam = await canliKonumEkle(govde, (m) => {
                  hata = m;
                });
                if (!tamam) return hata ?? t("kontrol.kabinSensoru.konum.kaydedilemedi");
                setFormAcik(false);
                await yenile();
                return null;
              }}
            />
          ) : null}
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  kart: {
    backgroundColor: colors.panel,
    borderRadius: rs(14),
    padding: rs(12),
    gap: rs(6),
    borderWidth: 1,
    borderColor: colors.border,
  },
  baslikSatiri: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  baslik: { flex: 1, color: colors.text, fontSize: rf(14), fontWeight: "700" },
  deger: { color: colors.cyan, fontSize: rf(16), fontWeight: "800" },
  aciklama: { color: colors.textMuted, fontSize: rf(11) },
  uyari: { color: colors.warning, fontSize: rf(11), fontWeight: "700" },
  konumSatiri: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.sm },
  konum: { flex: 1, color: colors.text, fontSize: rf(12) },
  dugme: {
    minHeight: touch.min,
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.cyan,
    borderRadius: rs(8),
    paddingHorizontal: rs(10),
  },
  dugmeMetni: { color: colors.cyan, fontSize: rf(12), fontWeight: "700" },
});
