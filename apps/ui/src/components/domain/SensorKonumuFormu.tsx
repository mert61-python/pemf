// Author: mertaygn, cglrgrkn
/**
 * SENSÖR KONUMU FORMU — Y308 (sahip 19-11): kabin sensörünün (MLX) konumu İSTEĞE BAĞLI. Sol çıkıntıdan cm + ön çıkıntıdan cm + tabandan
 * yükseklik cm + isteğe bağlı not → "Kaydet" (konumlu) ya da "Serbest (konumsuz)". Seans sonrası kullanımda başlangıç saati de seçilir.
 * Ölçü kuralı Doğrula'nınkiyle AYNI (çıkıntı kenarından). Modal DEĞİL (satır içi) — masaüstü + telefon aynı; ACİL DURDUR'u örtmez.
 * TR klavyede ondalık virgül kabul edilir ("2,5").
 */
import { useState } from "react";
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";
import { colors, rf, rs, spacing, touch } from "@/theme/tokens";
import type { SensorKonumuGovde, SensorKonumuKaydi } from "@/services/sensorKonumu";

const sayi = (s: string) => Number(String(s).trim().replace(",", "."));
const sayiMetni = (v: number | null | undefined) => (v === null || v === undefined ? "" : String(v));
const saatMetni = (epoch: number) => new Date(epoch * 1000).toTimeString().slice(0, 8);

/** "SS:DD(:ss)" → `tabanEpoch` gününde epoch (saniye); geçersizse null. */
export function saattenEpoch(saat: string, tabanEpoch: number): number | null {
  const m = /^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$/.exec(saat);
  if (!m) return null;
  const [h, dk, sn] = [Number(m[1]), Number(m[2]), Number(m[3] ?? 0)];
  if (h > 23 || dk > 59 || sn > 59) return null;
  const d = new Date(tabanEpoch * 1000);
  d.setHours(h, dk, sn, 0);
  return d.getTime() / 1000;
}

export function SensorKonumuFormu({
  onKaydet,
  onVazgec,
  ilk = null,
  tasindi = false,
  baslangicTabani,
  testID = "sensor-konumu-formu",
}: {
  /** Gövdeyi gönderir; hata metni döner (başarıda null). */
  onKaydet: (govde: SensorKonumuGovde) => Promise<string | null>;
  onVazgec: () => void;
  /** Düzeltilen giriş (alanlar dolu gelir). */
  ilk?: SensorKonumuKaydi | null;
  /** Canlıda önceki konum varsa düğme "Sensörü taşıdım". */
  tasindi?: boolean;
  /** Seans SONRASI: başlangıç saati seçilir (seansın başladığı gün / an). Verilmezse sunucu saati (canlı). */
  baslangicTabani?: number;
  testID?: string;
}) {
  const { t } = useTranslation();
  const [sol, setSol] = useState(sayiMetni(ilk?.sol_cm));
  const [on, setOn] = useState(sayiMetni(ilk?.on_cm));
  const [yuk, setYuk] = useState(sayiMetni(ilk?.yukseklik_cm));
  const [not, setNot] = useState(ilk?.not_metni ?? "");
  const [saat, setSaat] = useState(
    baslangicTabani !== undefined ? saatMetni(ilk?.zaman_epoch ?? baslangicTabani) : "",
  );
  const [hata, setHata] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);

  const gonder = async (serbest: boolean) => {
    const govde: SensorKonumuGovde = serbest
      ? { serbest: true, notMetni: not.trim() }
      : { serbest: false, solCm: sayi(sol), onCm: sayi(on), yukseklikCm: sayi(yuk), notMetni: not.trim() };
    if (baslangicTabani !== undefined) {
      const z = saattenEpoch(saat, baslangicTabani);
      if (z === null) {
        setHata(t("kontrol.kabinSensoru.konum.saatGecersiz"));
        return;
      }
      govde.zamanEpoch = z;
    }
    setMesgul(true);
    setHata(null);
    const h = await onKaydet(govde);
    setMesgul(false);
    if (h) setHata(h);
  };

  const alan = (etiket: string, deger: string, degis: (v: string) => void, id: string, klavye: "decimal-pad" | "default") => (
    <View style={styles.alan}>
      <Text style={styles.etiket}>{etiket}</Text>
      <TextInput
        style={styles.girdi}
        value={deger}
        onChangeText={degis}
        keyboardType={klavye}
        accessibilityLabel={etiket}
        testID={id}
      />
    </View>
  );

  return (
    <View style={styles.form} testID={testID}>
      <Text style={styles.aciklama}>{t("kontrol.kabinSensoru.konum.aciklama")}</Text>
      <View style={styles.satir}>
        {alan(t("kontrol.kabinSensoru.konum.sol"), sol, setSol, "sensor-konumu-sol", "decimal-pad")}
        {alan(t("kontrol.kabinSensoru.konum.on"), on, setOn, "sensor-konumu-on", "decimal-pad")}
        {alan(t("kontrol.kabinSensoru.konum.yukseklik"), yuk, setYuk, "sensor-konumu-yukseklik", "decimal-pad")}
      </View>
      {baslangicTabani !== undefined
        ? alan(t("kontrol.kabinSensoru.konum.baslangic"), saat, setSaat, "sensor-konumu-saat", "default")
        : null}
      {alan(t("kontrol.kabinSensoru.konum.not"), not, setNot, "sensor-konumu-not", "default")}
      {hata ? (
        <Text style={styles.hata} testID="sensor-konumu-hata">
          {hata}
        </Text>
      ) : null}
      <View style={styles.dugmeler}>
        <TouchableOpacity
          style={[styles.dugme, styles.ana]}
          disabled={mesgul}
          onPress={() => gonder(false)}
          accessibilityRole="button"
          testID="sensor-konumu-kaydet"
        >
          <Text style={styles.dugmeMetni}>
            {tasindi ? t("kontrol.kabinSensoru.konum.tasidim") : t("kontrol.kabinSensoru.konum.kaydet")}
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.dugme}
          disabled={mesgul}
          onPress={() => gonder(true)}
          accessibilityRole="button"
          testID="sensor-konumu-serbest"
        >
          <Text style={styles.dugmeMetni}>{t("kontrol.kabinSensoru.konum.serbest")}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.dugme} onPress={onVazgec} accessibilityRole="button" testID="sensor-konumu-vazgec">
          <Text style={styles.dugmeMetni}>{t("kontrol.kabinSensoru.konum.vazgec")}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  form: { gap: rs(6), paddingTop: rs(6), borderTopWidth: 1, borderTopColor: colors.border },
  aciklama: { color: colors.textMuted, fontSize: rf(11) },
  satir: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  alan: { minWidth: rs(110), flexGrow: 1, gap: rs(2) },
  etiket: { color: colors.textMuted, fontSize: rf(11) },
  girdi: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: rs(8),
    paddingHorizontal: rs(8),
    paddingVertical: rs(6),
    color: colors.text,
    fontSize: rf(13),
  },
  hata: { color: colors.warning, fontSize: rf(12), fontWeight: "700" },
  dugmeler: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  dugme: {
    minHeight: touch.min,
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: rs(8),
    paddingHorizontal: rs(10),
  },
  ana: { backgroundColor: colors.primary, borderColor: colors.primary },
  dugmeMetni: { color: colors.text, fontSize: rf(12), fontWeight: "700" },
});
