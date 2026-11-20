// Author: mertaygn, cglrgrkn
/**
 * SEANS DETAYI — KABİN SENSÖRÜ KONUM DİLİMLERİ (Y308, sahip 19-11): konum girişi varsa ölçümler konum DİLİMLERİNE ayrılır — dilim
 * başına konum, süre, ortalama / en yüksek mT ve konumlu dilimde aynı noktada aynı sürüşle ODAK alan modelinin TAHMİNİ + fark %;
 * serbest dilimde tahmin YOK (backend `servers/sensor_konumu.dilimler` — PDF / CSV ile AYNI tablo). Girilmeyi unutulan konum seans
 * bittikten sonra burada girilir / düzeltilir (başlangıç saati seçilerek). Hiç giriş yoksa yalnız "Sensör konumu ekle" düğmesi (kabin
 * sensörü alan ölçtüyse) — ölçüm görünümü bugünküyle BİREBİR. Masaüstü + telefon aynı; ondalık dile göre.
 */
import { useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";
import { colors, rf, rs, spacing, touch } from "@/theme/tokens";
import { ondalikMetni } from "@/i18n/dil";
import { SensorKonumuFormu } from "@/components/domain/SensorKonumuFormu";
import { konumOzeti } from "@/components/domain/KabinSensoruKarti";
import { gecmisKonumEkle, gecmisKonumSil, type KonumDilimi, type SensorKonumuKaydi } from "@/services/sensorKonumu";

const saat = (epoch: number) => new Date(epoch * 1000).toTimeString().slice(0, 8);

export function KonumDilimleriBolumu({
  seansId,
  baslangicEpoch,
  konumlar,
  dilimler,
  alanVar,
  onDegisti,
}: {
  seansId: number | string;
  baslangicEpoch: number | null;
  konumlar: SensorKonumuKaydi[];
  dilimler: KonumDilimi[];
  /** Kabin sensörü bu seansta alan ölçtü mü (giriş yokken düğme yalnız o zaman). */
  alanVar: boolean;
  onDegisti: () => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<{ ilk: SensorKonumuKaydi | null } | null>(null);
  if (!konumlar.length && !alanVar) return null;
  const taban = baslangicEpoch ?? konumlar[0]?.zaman_epoch ?? Date.now() / 1000;
  const mT = (v: number | null) => (v === null ? "—" : ondalikMetni(v, 2));

  const kaydet = async (govde: Parameters<typeof gecmisKonumEkle>[1]) => {
    let hata: string | null = null;
    const tamam = await gecmisKonumEkle(seansId, govde, (m) => {
      hata = m;
    });
    if (!tamam) return hata ?? t("kontrol.kabinSensoru.konum.kaydedilemedi");
    // Düzeltme = yeni giriş + eskisinin silinmesi (önce ekle: silme düşerse veri kaybolmaz, çift giriş görünür ve silinebilir).
    if (form?.ilk) await gecmisKonumSil(seansId, form.ilk.id);
    setForm(null);
    onDegisti();
    return null;
  };

  return (
    <View style={styles.bolum} testID="seans-konum-bolumu">
      <Text style={styles.baslik}>{t("seans.detay.konum.baslik")}</Text>
      {dilimler.map((d, i) => (
        <View key={`${d.baslangic_epoch}-${i}`} style={styles.dilim} testID={`konum-dilimi-${i}`}>
          <Text style={styles.satir}>
            {`${saat(d.baslangic_epoch)} · ${t("seans.detay.konum.sure", { dk: Math.floor(d.sure_sn / 60), sn: Math.round(d.sure_sn % 60) })} · `}
            {konumOzeti(t, d.serbest ? null : { id: 0, zaman_epoch: d.baslangic_epoch, serbest: false, sol_cm: d.sol_cm, on_cm: d.on_cm, yukseklik_cm: d.yukseklik_cm, not_metni: d.not })}
          </Text>
          <Text style={styles.satir}>{t("seans.detay.konum.olcum", { ort: mT(d.ortalama_mt), tepe: mT(d.tepe_mt) })}</Text>
          <Text style={styles.satirSoluk} testID={`konum-dilimi-tahmin-${i}`}>
            {d.tahmin_mt === null
              ? d.serbest
                ? t("seans.detay.konum.tahminYokSerbest")
                : t("seans.detay.konum.tahminYok")
              : t("seans.detay.konum.tahmin", {
                  tahmin: mT(d.tahmin_mt),
                  fark: d.fark_yuzde === null ? "—" : t("ai.ortak.yuzde", { deger: ondalikMetni(d.fark_yuzde, 1) }),
                })}
          </Text>
          {d.not ? <Text style={styles.satirSoluk}>{d.not}</Text> : null}
        </View>
      ))}
      {konumlar.map((k) => (
        <View key={k.id} style={styles.giris} testID={`konum-girisi-${k.id}`}>
          <Text style={[styles.satir, { flex: 1 }]}>{`${saat(k.zaman_epoch)} · ${konumOzeti(t, k)}`}</Text>
          <TouchableOpacity style={styles.dugme} onPress={() => setForm({ ilk: k })} accessibilityRole="button" testID={`konum-duzelt-${k.id}`}>
            <Text style={styles.dugmeMetni}>{t("seans.detay.konum.duzelt")}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.dugme}
            onPress={async () => {
              if (await gecmisKonumSil(seansId, k.id)) onDegisti();
            }}
            accessibilityRole="button"
            testID={`konum-sil-${k.id}`}
          >
            <Text style={styles.dugmeMetni}>{t("seans.detay.konum.sil")}</Text>
          </TouchableOpacity>
        </View>
      ))}
      {form ? (
        <SensorKonumuFormu ilk={form.ilk} baslangicTabani={taban} onVazgec={() => setForm(null)} onKaydet={kaydet} testID="seans-konum-formu" />
      ) : (
        <TouchableOpacity style={styles.dugme} onPress={() => setForm({ ilk: null })} accessibilityRole="button" testID="seans-konum-ekle">
          <Text style={styles.dugmeMetni}>{t("seans.detay.konum.ekle")}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  bolum: { gap: rs(6), marginTop: spacing.sm },
  baslik: { color: colors.text, fontSize: rf(14), fontWeight: "700" },
  dilim: { borderWidth: 1, borderColor: colors.border, borderRadius: rs(8), padding: rs(8), gap: rs(2) },
  satir: { color: colors.text, fontSize: rf(12) },
  satirSoluk: { color: colors.textMuted, fontSize: rf(11) },
  giris: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.sm },
  dugme: {
    minHeight: touch.min,
    justifyContent: "center",
    alignSelf: "flex-start",
    borderWidth: 1,
    borderColor: colors.cyan,
    borderRadius: rs(8),
    paddingHorizontal: rs(10),
  },
  dugmeMetni: { color: colors.cyan, fontSize: rf(12), fontWeight: "700" },
});
