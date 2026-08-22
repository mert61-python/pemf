// Author: mertaygn, cglrgrkn
/**
 * MOBİL AÇILIŞ KAPISI (2026-08-16 sahip isteği: "mobil uygulamada da aynısını istiyorum —
 * önce güncelleme kontrolü, sonra açılış ve kullanım").
 *
 * Masaüstü client'ta 1.9.30 ile "Başlat" düğmesi güncelleme kontrolü bitmeden çıkmıyor. Mobilde
 * karşılığı YOKTU: uygulama anında açılıyor, güncelleme ancak içerideki bantla — kullanıcı fark
 * ederse — görülüyordu. Bu kapı kontrolü açılışın ÖNÜNE alır.
 *
 * ⚠️ MOBİLDE GÜNCELLEME ZORUNLU KILINAMAZ — masaüstünden ayrılan TEK nokta budur ve kasıtlıdır.
 * Masaüstünde kurulumu client'ın kendisi yapar, sonra düğmeyi açar. Android'de kurulumu İŞLETİM
 * SİSTEMİ sorar; kullanıcı reddedebilir, "bilinmeyen kaynak" izni hiç verilmemiş olabilir ya da
 * kurumsal profil bunu yasaklamış olabilir. Zorunlu tutmak, tıbbi bir cihazın uzaktan kumandasını
 * KALICI OLARAK kilitlemek demekti. Bu yüzden güncelleme ekranında HER ZAMAN "Şimdilik devam et"
 * vardır — kapı bir hız kesici, kilit değil.
 *
 * ⚠️ HASTA GÜVENLİĞİ — kapı yalnız SOĞUK AÇILIŞTA çalışır; seans izlenirken uygulama zaten
 * açıktır. Yine de cihazda seans SÜRÜYOR olabilir ve operatör telefonu ACİL DURDUR için açıyor
 * olabilir. Bu yüzden içeri giren yol hiçbir koşulda tıkanmaz:
 *   * kontrol {@link KONTROL_ZAMAN_ASIMI_MS} ile sınırlı,
 *   * {@link ATLA_GORUNME_MS} sonra "Atla" çıkar,
 *   * ağ/manifest hatası ve Android DIŞI platformlar kapıyı hiç kapatmaz,
 *   * güncelleme ekranında "Şimdilik devam et" indirme sürerken de durur.
 * Atlanan kontrol kaybolmaz: `MobileUpdateBanner` içeride aynı güncellemeyi yakalar.
 *
 * ⚠️ GEÇ GELEN SONUÇ EKRANI GERİ ALMAZ. Kapı bir kez açıldıktan sonra (zaman aşımı ya da "Atla")
 * kontrol tamamlansa bile güncelleme ekranına DÖNÜLMEZ. Masaüstünde düzeltilen asıl arıza tam
 * olarak buydu: kullanıcı tam dokunacakken ekranın altından kayması.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Platform,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { Download } from "lucide-react-native";

import { useApkGuncelleme } from "@/hooks/useApkGuncelleme";
import { guncellemeVarMi, guncellemeyiAtla, kurulumunuErtele, type MobilSurum } from "@/services/mobileUpdate";
import { colors, radius, rf, rs, spacing } from "@/theme/tokens";

/** Uygulama ikonu — AuthScreen/AppShell ile AYNI kaynak (tek görsel kimlik). */
const LOGO = require("../../../assets/icon.png");

/**
 * Kontrolün üst sınırı. ÖLÇÜM (2026-08-16, sabit hat): manifest 5.098 B, 1 yönlendirme, 2 TLS
 * el sıkışması → 0,63 / 0,63 / 0,75 / 0,90 / 0,99 s. Mobil şebekede bunun birkaç katı olabilir;
 * 7 s ölçülen en kötünün ~7 katı. Aşılırsa kapı AÇILIR — kontrol arka planda sürer ve sonucu
 * uygulama içindeki bant gösterir, yani bekleyerek kazanılacak bir şey kalmaz.
 */
export const KONTROL_ZAMAN_ASIMI_MS = 7000;

/**
 * "Atla"nın görünme anı. Normal kontrol ölçüme göre ≤1 s'de biter → sıradan kullanıcı bu
 * düğmeyi HİÇ görmez. Acelesi olan (ör. seansı durdurmak isteyen operatör) en geç 2,5 saniyede
 * içeri girebilir.
 */
export const ATLA_GORUNME_MS = 2500;

type Durum = "kontrol" | "guncelleme" | "acik";

/** Bayt → "54 MB" (mobil kota görünür olsun). */
function mb(bayt: number): string {
  return `${Math.round(bayt / 1_000_000)} MB`;
}

export function MobileUpdateGate({ children }: { children: React.ReactNode }) {
  // Android DIŞI (web + iOS): kapı hiç kurulmaz. Web'i masaüstü client güncelliyor, iOS'ta
  // doğrudan APK kurulumu yok → beklemenin karşılığı sıfır olurdu.
  const [durum, setDurum] = useState<Durum>(() =>
    Platform.OS === "android" ? "kontrol" : "acik",
  );
  const [atlaGorunur, setAtlaGorunur] = useState(false);
  const [surum, setSurum] = useState<MobilSurum | null>(null);
  const bittiRef = useRef(false);

  const { oran, hata, bilgi, kurulumAcildi, paketHazir, guncelle } = useApkGuncelleme(surum);

  /** Kapıyı aç ve BİR DAHA kapanmayacağını işaretle (geç gelen sonuç ekranı geri almasın). */
  const kapiyiAc = useCallback(() => {
    bittiRef.current = true;
    setDurum("acik");
  }, []);

  useEffect(() => {
    if (Platform.OS !== "android") return;
    const zamanAsimi = setTimeout(() => {
      if (!bittiRef.current) kapiyiAc();
    }, KONTROL_ZAMAN_ASIMI_MS);
    const atlaTimer = setTimeout(() => setAtlaGorunur(true), ATLA_GORUNME_MS);

    void (async () => {
      const r = await guncellemeVarMi();
      if (bittiRef.current) return; // zaman aşımı/Atla ile ZATEN açıldı → ekranı geri ALMA
      bittiRef.current = true;
      clearTimeout(zamanAsimi);
      if (r.varMi && r.surum) {
        setSurum(r.surum);
        setDurum("guncelleme");
      } else {
        setDurum("acik");
      }
    })();

    return () => {
      bittiRef.current = true;
      clearTimeout(zamanAsimi);
      clearTimeout(atlaTimer);
    };
  }, [kapiyiAc]);

  const simdilikDevam = useCallback(() => {
    // ⚠️ Bant-susturma yalnız HİÇBİR ŞEY BAŞLAMADIYSA işaretlenir. İndirme sürüyor ya da paket
    // tam inmişse ([5.7c]: oran===null "hiç başlamadı"yı "tamamlandı"dan ayıramazdı) bandı
    // susturmak, paketi kurmanın tek yolunu da kapatırdı; bant durur ki tek dokunuşla sürsün.
    // [5.7a] O iki durumda ise KURULUM-ERTELEMESİ konur: uçuşta kalan guncelle() indirme
    // bitince yükleyiciyi kullanıcının o anki işinin üstüne SORMADAN açamaz.
    if (surum) {
      if (oran === null && !paketHazir) guncellemeyiAtla(surum.versionCode);
      else kurulumunuErtele(surum.versionCode);
    }
    kapiyiAc();
  }, [surum, oran, paketHazir, kapiyiAc]);

  if (durum === "acik") return <>{children}</>;

  const indiriliyor = oran !== null;

  return (
    <View style={styles.root} testID="mobil-acilis-kapisi">
      <Image source={LOGO} style={styles.logo} resizeMode="contain" />
      <Text style={styles.marka}>PEMF Vet</Text>

      {durum === "kontrol" ? (
        <>
          <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: spacing.lg }} />
          <Text style={styles.durum}>Güncelleme kontrol ediliyor…</Text>
          {atlaGorunur ? (
            <TouchableOpacity
              onPress={kapiyiAc}
              style={styles.atla}
              testID="kapi-atla"
              accessibilityRole="button"
              accessibilityLabel="Güncelleme kontrolünü atla ve uygulamayı aç"
            >
              <Text style={styles.atlaText}>Atla</Text>
            </TouchableOpacity>
          ) : null}
        </>
      ) : (
        <View style={styles.kart}>
          <View style={styles.baslikSatiri}>
            <Download color={colors.cyan} size={rs(18)} />
            <Text style={styles.baslik}>Yeni sürüm hazır: {surum?.version}</Text>
          </View>
          <Text style={[styles.alt, hata ? styles.altHata : null]}>
            {hata ||
              bilgi ||
              (indiriliyor
                ? // ⚠️ Yalnız yüzde YETMEZ: 128 MB'lık bir paketde kullanıcı ne kadar veri
                  // harcadığını da görmeli (mobil kota). MB'ler manifest boyutundan türetilir.
                  `İndiriliyor… %${Math.round((oran ?? 0) * 100)} · ${mb((oran ?? 0) * (surum?.size ?? 0))} / ${mb(surum?.size ?? 0)}`
                : surum?.notes || "Kullanmadan önce güncellemeniz önerilir.")}
          </Text>

          {indiriliyor ? (
            <View style={styles.barDis}>
              <View style={[styles.barIc, { width: `${Math.round((oran ?? 0) * 100)}%` }]} />
            </View>
          ) : (
            <TouchableOpacity
              style={styles.btn}
              onPress={guncelle}
              testID="kapi-guncelle"
              accessibilityRole="button"
              accessibilityLabel={`Sürüm ${surum?.version} güncellemesini indir ve kur`}
            >
              {/* Kurulum bir kez açıldıysa düğme "tekrar dene" işlevindedir; aynı metni bırakmak
                  kullanıcıya hiçbir şey olmamış gibi görünürdü. İkinci dokunuş İNDİRMEZ:
                  dosya diskte tamdır, doğrudan yükleyici açılır. */}
              <Text style={styles.btnText}>{kurulumAcildi ? "Kurulumu tekrar aç" : "Güncelle ve kur"}</Text>
            </TouchableOpacity>
          )}

          {/* ⚠️ İNDİRME SÜRERKEN DE DURUR — 128 MB'lık paket mobil şebekede dakikalar sürebilir;
              kullanıcıyı o süre boyunca uygulamanın dışında tutmak kabul edilemez. Ayrılırsa
              indirme diskte kalır, bant kaldığı yerden sürdürür. */}
          <TouchableOpacity
            onPress={simdilikDevam}
            style={styles.atla}
            testID="kapi-devam"
            accessibilityRole="button"
            accessibilityLabel="Güncellemeyi ertele ve uygulamayı aç"
          >
            <Text style={styles.atlaText}>Şimdilik devam et</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xl,
  },
  logo: { width: rs(86), height: rs(86), borderRadius: radius.card },
  marka: { color: colors.text, fontSize: rf(20), fontWeight: "800", marginTop: spacing.md },
  durum: { color: colors.textMuted, fontSize: rf(13), marginTop: spacing.md, textAlign: "center" },
  atla: { marginTop: spacing.lg, paddingVertical: rs(11), paddingHorizontal: spacing.lg, minHeight: rs(44), justifyContent: "center" },
  atlaText: { color: colors.textSubtle, fontSize: rf(12), fontWeight: "700", textAlign: "center" },
  kart: {
    width: "100%",
    maxWidth: rs(420),
    marginTop: spacing.lg,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.card,
    padding: spacing.lg,
  },
  baslikSatiri: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  baslik: { color: colors.text, fontSize: rf(14), fontWeight: "800", flex: 1 },
  alt: { color: colors.textMuted, fontSize: rf(12), marginTop: spacing.sm, lineHeight: rf(17) },
  altHata: { color: colors.warning },
  btn: {
    backgroundColor: colors.cyan,
    borderRadius: radius.btn,
    marginTop: spacing.lg,
    paddingVertical: rs(12),
    minHeight: rs(48),
    justifyContent: "center",
  },
  btnText: { color: "#04121F", fontWeight: "800", fontSize: rf(13), textAlign: "center" },
  barDis: {
    height: rs(8),
    borderRadius: radius.full,
    backgroundColor: colors.bgAlt,
    marginTop: spacing.lg,
    overflow: "hidden",
  },
  barIc: { height: "100%", backgroundColor: colors.cyan, borderRadius: radius.full },
});
