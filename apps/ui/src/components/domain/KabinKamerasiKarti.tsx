/**
 * "Kabin kamerası" bölümü (T2D-2 · Tezgâh-2 #3; T3 · Y190 sahip 2026-10-24: "kamera seçimi de burada olmalı, ayarlar içinde değil")
 * — petri / fantom analiz panelinde ve AI Pro panelinde, YALNIZ backend bu makinedeyken (`kabinKamerasiKullanilir`; kamera backend'in
 * makinesine bağlı). Ayarlar'dan KALKTI. `kilitli` (canlı kamera / hazırlık / seans kamerayı tutarken): tarama ve seçim yapılmaz.
 *
 * AI Pro önizlemesi / seansı, petri / fantom "Fotoğraf Çek" ve "Canlı Kamera" kamerayı sabit "0 numara" ile değil buradaki seçimle
 * açar (dizüstünde 0 = dahili kamera).
 * Seçim cihazda saklanır (`/settings/kabin-kamerasi`, hesaptan / profilden bağımsız); seçim yoksa AI Pro kamerası açılmaz ve kart
 * bunu eylem söyleyerek gösterir. OpenCV kamera adı vermediği için tarama her kameradan küçük bir önizleme getirir — kullanıcı kabin
 * kamerasını görüntüden tanır. Tarama yalnız düğmeyle (kamera ışığı kısa yanar); hata iletisi sunucudan (eylem söyler).
 */
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Image, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useTranslation } from "react-i18next";
import { Camera } from "lucide-react-native";
import { colors, radius, spacing, touch, typography } from "@/theme/tokens";
import { apiGet, apiPost, KAMERA_TIMEOUT_MS } from "@/services/apiClient";
// T3 · Y190: bölüm AI Pro panelinde de çizilir; panel ToastProvider gerektirmez → bildirim köprüden (sağlayıcı yoksa sessiz;
// seçimin kendisi bölümdeki "Seçili kamera" satırında zaten görünür).
import { emitToast } from "@/services/toastBridge";

interface Secim {
  indeks: number;
  kaynak?: "ayar" | "ortam";
  /** KD-2: kamera kimliği (Windows adı + VID/PID) — seçim buna bağlı; MSMF sırası değişse de aynı kamera açılır. */
  kimlik?: { ad?: string | null; vidpid?: string | null } | null;
}
interface Aday {
  indeks: number;
  ad?: string | null;
  vidpid?: string | null;
  genislik: number;
  yukseklik: number;
  onizleme: string | null;
}

export function KabinKamerasiKarti({ kilitli = false }: { kilitli?: boolean }) {
  const { t } = useTranslation();
  const [secili, setSecili] = useState<Secim | null>(null);
  const [yuklendi, setYuklendi] = useState(false);
  const [adaylar, setAdaylar] = useState<Aday[] | null>(null);
  const [taraniyor, setTaraniyor] = useState(false);

  const yukle = useCallback(async () => {
    const r = await apiGet<{ secili: Secim | null } | null>("/settings/kabin-kamerasi", null, { silent: true });
    setSecili(r?.secili ?? null);
    setYuklendi(r !== null);
  }, []);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const tara = async () => {
    if (kilitli) return;
    setTaraniyor(true);
    try {
      // KD madde 0: kamera açılışı genel 8 sn sınırına bağlı değil (yavaş sürücüde "bağlı değil" sanılıyordu); zaman aşımı metni
      // KAMERAYA özgü ("model yüklemesi" DEĞİL).
      const r = await apiPost<{ kameralar: Aday[]; secili: Secim | null } | null>("/settings/kabin-kamerasi/tara", {}, null, {
        timeoutMs: KAMERA_TIMEOUT_MS,
        zamanAsimiMesaji: t("ayarlar.kabinKamerasi.taramaZamanAsimi"),
      });
      if (r) {
        setAdaylar(r.kameralar);
        setSecili(r.secili);
      }
    } finally {
      setTaraniyor(false);
    }
  };

  const sec = async (indeks: number) => {
    if (kilitli) return;
    const r = await apiPost<{ secili: Secim } | null>("/settings/kabin-kamerasi", { indeks }, null);
    if (r?.secili) {
      setSecili(r.secili);
      emitToast(t("ayarlar.kabinKamerasi.secildi", { indeks }), "success");
    }
  };

  return (
    <View style={styles.kutu} testID="kabin-kamerasi-bolumu">
      <View style={styles.baslikSatiri}>
        <Camera color={colors.primary} size={20} />
        <Text style={styles.baslik}>{t("ayarlar.kabinKamerasi.baslik")}</Text>
      </View>
      <Text style={styles.aciklama}>{t("ayarlar.kabinKamerasi.aciklama")}</Text>
      {yuklendi ? (
        secili ? (
          <Text style={styles.durum} testID="kabin-kamerasi-secili">
            {secili.kimlik?.ad
              ? t("ayarlar.kabinKamerasi.seciliKameraAdli", { indeks: secili.indeks, ad: secili.kimlik.ad, vidpid: secili.kimlik.vidpid ?? "?" })
              : t("ayarlar.kabinKamerasi.seciliKamera", { indeks: secili.indeks })}
          </Text>
        ) : (
          <Text style={[styles.durum, styles.uyari]} testID="kabin-kamerasi-secilmedi">
            {t("ayarlar.kabinKamerasi.secilmedi")}
          </Text>
        )
      ) : null}
      <TouchableOpacity
        style={[styles.dugme, kilitli && styles.kilitli]}
        onPress={() => void tara()}
        disabled={taraniyor || kilitli}
        accessibilityRole="button"
        accessibilityState={{ disabled: taraniyor || kilitli }}
        testID="kabin-kamerasi-tara"
      >
        {taraniyor ? <ActivityIndicator color="#fff" /> : <Text style={styles.dugmeMetni}>{t("ayarlar.kabinKamerasi.tara")}</Text>}
      </TouchableOpacity>
      {taraniyor ? (
        <Text style={styles.aciklama} testID="kabin-kamerasi-taraniyor">
          {t("ayarlar.kabinKamerasi.taraniyor")}
        </Text>
      ) : null}
      {adaylar && adaylar.length === 0 ? <Text style={styles.aciklama}>{t("ayarlar.kabinKamerasi.bulunamadi")}</Text> : null}
      {adaylar?.map((a) => (
        <View key={a.indeks} style={styles.aday} testID={`kabin-kamerasi-aday-${a.indeks}`}>
          {a.onizleme ? (
            <Image source={{ uri: `data:image/jpeg;base64,${a.onizleme}` }} style={styles.onizleme} resizeMode="contain" />
          ) : null}
          <View style={styles.adayMetin}>
            <Text style={styles.adayBaslik}>
              {a.ad
                ? t("ayarlar.kabinKamerasi.kameraAdiTam", { indeks: a.indeks, ad: a.ad, vidpid: a.vidpid ?? "?" })
                : t("ayarlar.kabinKamerasi.kameraAdi", { indeks: a.indeks })}
            </Text>
            <Text style={styles.aciklama}>{t("ayarlar.kabinKamerasi.cozunurluk", { genislik: a.genislik, yukseklik: a.yukseklik })}</Text>
          </View>
          <TouchableOpacity
            style={[styles.secenek, secili?.indeks === a.indeks && styles.secenekSecili, kilitli && styles.kilitli]}
            onPress={() => void sec(a.indeks)}
            disabled={kilitli}
            accessibilityRole="button"
            accessibilityState={{ selected: secili?.indeks === a.indeks, disabled: kilitli }}
            testID={`kabin-kamerasi-sec-${a.indeks}`}
          >
            <Text style={[styles.secenekMetni, secili?.indeks === a.indeks && styles.secenekMetniSecili]}>
              {secili?.indeks === a.indeks ? t("ayarlar.kabinKamerasi.seciliEtiket") : t("ayarlar.kabinKamerasi.bunuSec")}
            </Text>
          </TouchableOpacity>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  kutu: {
    marginVertical: spacing.sm,
    gap: spacing.sm,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
  },
  kilitli: { opacity: 0.5 },
  baslikSatiri: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  baslik: { fontSize: typography.body, fontWeight: "700", color: colors.text },
  aciklama: { fontSize: typography.caption, color: colors.textMuted },
  durum: { fontSize: typography.body, color: colors.text, fontWeight: "600" },
  uyari: { color: colors.danger },
  dugme: {
    minHeight: touch.min,
    borderRadius: radius.md,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.lg,
    alignSelf: "flex-start",
  },
  dugmeMetni: { color: "#fff", fontWeight: "700" },
  aday: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" },
  onizleme: { width: 120, height: 68, borderRadius: radius.sm, backgroundColor: colors.border },
  adayMetin: { flex: 1, minWidth: 120 },
  adayBaslik: { fontSize: typography.body, fontWeight: "700", color: colors.text },
  secenek: {
    minHeight: touch.min,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  secenekSecili: { backgroundColor: colors.primary },
  secenekMetni: { color: colors.primary, fontWeight: "700" },
  secenekMetniSecili: { color: "#fff" },
});
