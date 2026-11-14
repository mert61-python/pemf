// Author: mertaygn
/**
 * SurusKipiSecici — bobin başına BİPOLAR / UNİPOLAR sürüş kipi seçimi.
 *
 * ── NE YAPAR ────────────────────────────────────────────────────────────────
 * Bipolar: bir bobinin İKİ PWM'i (IN_A / IN_B) dönüşümlü darbelenir → akım her
 * yarım periyotta yön değiştirir, alan ±B arasında salınır.
 * Unipolar: yalnız IN_A darbelenir, IN_B kapalı kalır → akım tek yönlü, alan 0…+B.
 *
 * ── ⚠️ İSTEK ≠ ETKİN KİP (bu bileşenin var oluş sebebi) ─────────────────────
 * Bobin 6 (sağ duvar) ve 7 (sol duvar) sürücü devreleri DONANIMSAL olarak tek
 * yönlü — ikinci yarım köprü yok. Firmware `etkin = yetenek || istek` uygular:
 * bu ikisine "bipolar" istemek hiçbir şey değiştirmez. Bu yüzden onların düğmesi
 * KİLİTLİ gösterilir; kullanıcıya basabileceği ama işe yaramayan bir düğme
 * sunmak, sessizce yok sayılan bir komut demektir.
 *
 * Kartın GERÇEKTEN uyguladığı kip ACK'in `K=` alanından gelir ve `coil.unipolar`
 * olarak canlı duruma yazılır. Firmware bildirmediyse (eski sürüm) alan `null`
 * kalır → "kart bildirmedi" yazılır; `false` varsaymak "bipolar doğrulandı"
 * yalanı olurdu.
 *
 * ── ⚠️ KİP SÜRÜŞ ANINDA GİDER ───────────────────────────────────────────────
 * Hiçbir bobin çalışmıyorken keep-alive paket GÖNDERMEZ (boşta UART sessiz).
 * Seçim kaydedilir, bir sonraki başlatmada uygulanır. Bileşen bunu açıkça yazar.
 *
 * ── ⚠️ T-c (Tezgâh-2 #6): KUTULAR GERÇEKTEN BAŞLAR ─────────────────────────
 * Eskiden her açılışta sabit varsayılandan (1-5 BİP) başlıyordu: "Hepsi Unipolar"dan sonra sayfa / dil değişince kart UNİ
 * sürerken kutular BİP yazıyordu, fark yalnız kırmızı çerçeveydi. Artık kutular backend'in KAYITLI isteğinden
 * (`unipolarIstek` — bir sonraki sürüşte karta giden), o yoksa kartın bildirdiği kipten (`unipolar`) başlar ve kayıtlı
 * istek değişince (başka istemci) eşitlenir; kartın uyguladığı kip seçimden farklıysa bu METİNLE söylenir.
 */
import { useState, useCallback, useMemo, useEffect } from "react";
import { Text, View, StyleSheet, TouchableOpacity } from "react-native";
import { colors, spacing, typography, touch } from "@/theme/tokens";
import type { CoilStatus } from "@/types/domain";
import { apiPost, platformConfirm } from "@/services/apiClient";
import { STM_BOBIN_SAYISI as STM_BOBIN } from "@/services/bobinGorunurlugu";
import i18n from "i18next";
import { useTranslation } from "react-i18next";

/** TD6 · K8 (tezgâh Oturum 13): tek dokunuş, tam köprülü bobini DC bileşenli tek yönlü sürüşe KALICI geçiriyordu — onay ister.
 *  Ters yön (tek yönlüden çift yönlüye) firmware varsayılanına dönüştür; onay istemez. */
export const tekYonluOnayBaslik = (): string => i18n.t("kontrol.surus.tekYonluBaslik");
export const tekYonluOnayMetni = (): string => i18n.t("kontrol.surus.tekYonluMetni");

/** TD6 · K8: kaydedilen değişikliğin SONUÇ cümlesi — neyin değiştiğini söyler ("Kaydedildi" tek başına yetmiyordu). */
export function surusKipiSonucu(onceki: boolean[], yeni: boolean[], yetenekli: boolean[]): string {
  const tek: number[] = [];
  const cift: number[] = [];
  yeni.forEach((u, i) => {
    if (!yetenekli[i] || u === onceki[i]) return;
    (u ? tek : cift).push(i + 1);
  });
  const parca: string[] = [];
  if (tek.length) parca.push(i18n.t("kontrol.surus.tekYonluParca", { count: tek.length, liste: tek.join(", ") }));
  if (cift.length) parca.push(i18n.t("kontrol.surus.ciftYonluParca", { count: cift.length, liste: cift.join(", ") }));
  if (!parca.length) return i18n.t("kontrol.surus.kipDegismedi");
  return i18n.t("kontrol.surus.sonuc", { kisim: parca.join("; ") });
}

export function SurusKipiSecici({
  coils,
  stmConnected,
  disabled = false,
}: {
  coils: CoilStatus[];
  stmConnected: boolean;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const stmCoils = useMemo(
    () =>
      Array.from({ length: STM_BOBIN }, (_, i) => coils.find((c) => c.id === i + 1) ?? ({ id: i + 1 } as CoilStatus)),
    [coils],
  );

  // Yetenek: bipolar sürülebilen bobinler. A-65 (sahip): YALNIZ backend'in bildirdiği `bipolarYetenek` alanından — eski `id <= 5`
  // yedeği kalktı. Alan yoksa bipolar İSTENMEZ (kilitli): bildirilmeyen yetenek varsayılmaz.
  const bipolarYetenek = useCallback((c: CoilStatus) => c.bipolarYetenek === true, []);

  // Kullanıcı isteği. T-c: başlangıç backend'in KAYITLI isteği → yoksa kartın bildirdiği kip → yoksa varsayılan (yeteneksiz
  // bobin unipolar, yetenekli bipolar — firmware / backend varsayılanı `istenen maske = 0`).
  const [istek, setIstek] = useState<boolean[]>(() =>
    Array.from({ length: STM_BOBIN }, (_, i) => {
      const c = coils.find((k) => k.id === i + 1);
      if (typeof c?.unipolarIstek === "boolean") return c.unipolarIstek;
      if (typeof c?.unipolar === "boolean") return c.unipolar;
      return c?.bipolarYetenek !== true;
    }),
  );
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [durum, setDurum] = useState<string | null>(null);
  const yetenekliDizi = useMemo(() => stmCoils.map((c) => bipolarYetenek(c)), [stmCoils, bipolarYetenek]);

  // T-c: kayıtlı istek değişince (başka istemci / gönderimden sonra yayın) kutular backend'in gerçeğine eşitlenir. Gönderim
  // sürerken eşitlenmez (yanıt beklenir); gönderim düşerse kutular yine backend'deki (değişmemiş) isteğe döner.
  const sunucuIstegi = stmCoils.map((c) => (typeof c.unipolarIstek === "boolean" ? (c.unipolarIstek ? "1" : "0") : "-")).join("");
  useEffect(() => {
    if (gonderiliyor || sunucuIstegi.includes("-")) return;
    setIstek((eski) => {
      const yeni = sunucuIstegi.split("").map((x) => x === "1");
      return eski.length === yeni.length && eski.every((u, i) => u === yeni[i]) ? eski : yeni;
    });
  }, [sunucuIstegi, gonderiliyor]);

  const gonder = useCallback(
    async (yeni: boolean[]) => {
      const onceki = istek;
      // K8: yetenekli bir bobin çift yönlüden TEK YÖNLÜYE geçiyorsa onay; vazgeçilirse hiçbir şey değişmez/gönderilmez.
      if (yeni.some((u, i) => u && !onceki[i] && yetenekliDizi[i])) {
        const onay = await platformConfirm(tekYonluOnayBaslik(), tekYonluOnayMetni(), t("kontrol.surus.tekYonluYap"));
        if (!onay) return;
      }
      setIstek(yeni);
      setGonderiliyor(true);
      setDurum(null);
      try {
        const res = await apiPost<{ status?: string; etkin?: boolean[] } | null>(
          "/coil/surus_kipi",
          { unipolar: yeni },
          null, // fallback: ağ/HTTP hatasında null → aşağıdaki "Gönderilemedi" dalı
        );
        if (res?.status === "success") {
          setDurum(surusKipiSonucu(onceki, yeni, yetenekliDizi));
        } else {
          // ⚠️ Başarısızlık SESSİZ KALMAZ: istek geri alınmaz ama kullanıcı kipin
          // gitmediğini görür, yoksa arayüz "bipolar" gösterirken kart unipolar sürer.
          setDurum(t("kontrol.surus.gonderilemedi"));
        }
      } catch {
        /* istanbul ignore next -- SAVUNMA: apiPost fırlatmaz (fallback döner), sonuç eşlemesi saf */
        setDurum(t("kontrol.surus.gonderilemedi"));
      } finally {
        setGonderiliyor(false);
      }
    },
    [istek, yetenekliDizi, t],
  );

  const cevir = useCallback(
    (idx: number) => {
      const yeni = istek.slice();
      yeni[idx] = !yeni[idx];
      void gonder(yeni);
    },
    [istek, gonder],
  );

  const hepsi = useCallback(
    (unipolar: boolean) => {
      // Yeteneksiz bobin DAİMA unipolar kalır — "Hepsi Bipolar" onları da çevirir gibi
      // görünmesin diye istek dizisinde bile true bırakılır.
      void gonder(stmCoils.map((c) => (bipolarYetenek(c) ? unipolar : true)));
    },
    [stmCoils, bipolarYetenek, gonder],
  );

  const kilitli = disabled || gonderiliyor || !stmConnected;

  // T-c: kartın UYGULADIĞI kip seçimden farklı olan bobinler (kart bildirmediyse karşılaştırılmaz) — metinle söylenir.
  const farkli = stmCoils
    .filter((c, i) => typeof c.unipolar === "boolean" && c.unipolar !== (bipolarYetenek(c) ? istek[i] : true))
    .map((c) => c.id);

  return (
    <View style={styles.kok}>
      <Text style={styles.baslik}>{t("kontrol.surus.baslik")}</Text>
      <Text style={styles.altBaslik}>
        {t("kontrol.surus.aciklama")}
      </Text>

      <View style={styles.hepsiSatir}>
        <TouchableOpacity
          style={[styles.hepsiBtn, kilitli && styles.pasif]}
          onPress={() => hepsi(false)}
          disabled={kilitli}
          accessibilityRole="button"
          accessibilityLabel={t("kontrol.surus.hepsiBipolarEtiketi")}
        >
          <Text style={styles.hepsiMetin}>{t("kontrol.surus.hepsiBipolar")}</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.hepsiBtn, kilitli && styles.pasif]}
          onPress={() => hepsi(true)}
          disabled={kilitli}
          accessibilityRole="button"
          accessibilityLabel={t("kontrol.surus.hepsiUnipolarEtiketi")}
        >
          <Text style={styles.hepsiMetin}>{t("kontrol.surus.hepsiUnipolar")}</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.izgara}>
        {stmCoils.map((c, i) => {
          const yetenekli = bipolarYetenek(c);
          const uni = yetenekli ? istek[i] : true;
          // Kartın bildirdiği ETKİN kip. null/undefined → henüz bildirmedi.
          const etkin = typeof c.unipolar === "boolean" ? c.unipolar : null;
          const uyusmazlik = etkin !== null && etkin !== uni;
          return (
            <TouchableOpacity
              key={c.id}
              style={[
                styles.kutu,
                uni ? styles.kutuUni : styles.kutuBip,
                !yetenekli && styles.kutuKilitli,
                uyusmazlik && styles.kutuUyusmaz,
                kilitli && styles.pasif,
              ]}
              onPress={() => cevir(i)}
              disabled={kilitli || !yetenekli}
              hitSlop={touch.slopFor(spacing.sm)}
              accessibilityRole="button"
              accessibilityLabel={
                t("kontrol.surus.kutuEtiketi", { id: c.id, tip: uni ? t("kontrol.surus.tipUnipolar") : t("kontrol.surus.tipBipolar") }) +
                // A-65: "yalnız unipolar" yalnız backend `bipolarYetenek:false` BİLDİRDİYSE; alan yoksa yetenek bilinmiyor (yine kilitli).
                (yetenekli ? "" : c.bipolarYetenek === false ? t("kontrol.surus.kutuKilitli") : t("kontrol.surus.kutuYetenekBildirilmedi")) +
                (etkin === null ? t("kontrol.surus.kutuBildirmedi") : t("kontrol.surus.kutuUyguladi", { tip: etkin ? t("kontrol.surus.tipUnipolar") : t("kontrol.surus.tipBipolar") }))
              }
            >
              <Text style={styles.kutuNo}>{c.id}</Text>
              <Text style={styles.kutuKip}>{uni ? t("kontrol.surus.uni") : t("kontrol.surus.bip")}</Text>
              {!yetenekli && <Text style={styles.kutuKilit}>🔒</Text>}
            </TouchableOpacity>
          );
        })}
      </View>

      <Text style={styles.not}>
        {t("kontrol.surus.bobin67")}
      </Text>
      {stmCoils.every((c) => typeof c.unipolar !== "boolean") ? (
        <Text style={styles.not}>{t("kontrol.surus.uygulananKip")}</Text>
      ) : (
        <Text style={styles.not}>
          {t("kontrol.surus.uyguladigi")}{" "}
          {stmCoils
            .map((c) => `${c.id}:${typeof c.unipolar === "boolean" ? (c.unipolar ? t("kontrol.surus.uni") : t("kontrol.surus.bip")) : "—"}`)
            .join("  ")}
        </Text>
      )}
      {farkli.length > 0 && (
        <Text style={[styles.not, styles.uyusmazlik]}>
          {t("kontrol.surus.uyusmazlik", { count: farkli.length, liste: farkli.join(", ") })}
        </Text>
      )}
      {durum && <Text style={[styles.not, styles.durum]}>{durum}</Text>}
      {!stmConnected && <Text style={[styles.not, styles.durum]}>{t("kontrol.surus.stmBagliDegil")}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  kok: { gap: spacing.xs, marginTop: spacing.sm },
  baslik: { color: colors.text, fontWeight: "800", fontSize: typography.body },
  altBaslik: { color: colors.textSubtle, fontSize: typography.caption },
  hepsiSatir: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  hepsiBtn: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: 10,
    backgroundColor: colors.bgAlt,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    minHeight: touch.min,
    justifyContent: "center",
  },
  hepsiMetin: { color: colors.text, fontWeight: "700", fontSize: typography.caption },
  izgara: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", marginTop: spacing.xs },
  kutu: {
    width: touch.min + 8,
    height: touch.min,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
  },
  // Kip yalnız RENKLE anlatılmıyor: kutuda METİN de var (renk körlüğü + ekran görüntüsü).
  kutuBip: { backgroundColor: "#1d4ed8", borderColor: "#3b82f6" },
  kutuUni: { backgroundColor: colors.warningSoft, borderColor: colors.warning },
  kutuKilitli: { opacity: 0.75 },
  kutuUyusmaz: { borderColor: colors.danger, borderWidth: 2 },
  kutuNo: { color: colors.text, fontWeight: "800", fontSize: typography.caption },
  kutuKip: { color: colors.textMuted, fontWeight: "700", fontSize: 9 },
  kutuKilit: { fontSize: 9 },
  pasif: { opacity: 0.4 },
  not: { color: colors.textSubtle, fontSize: typography.caption },
  durum: { color: colors.textMuted },
  uyusmazlik: { color: colors.danger, fontWeight: "700" },
});
