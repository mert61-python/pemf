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
 */
import { useState, useCallback, useMemo } from "react";
import { Text, View, StyleSheet, TouchableOpacity } from "react-native";
import { colors, spacing, typography, touch } from "@/theme/tokens";
import type { CoilStatus } from "@/types/domain";
import { apiPost } from "@/services/apiClient";

/** STM sürücüsüne bağlı bobin sayısı (1..7). Backend `STM_COIL_IDS` ile AYNI olmalı. */
const STM_BOBIN = 7;

export function SurusKipiSecici({
  coils,
  stmConnected,
  disabled = false,
}: {
  coils: CoilStatus[];
  stmConnected: boolean;
  disabled?: boolean;
}) {
  const stmCoils = useMemo(
    () =>
      Array.from({ length: STM_BOBIN }, (_, i) => coils.find((c) => c.id === i + 1) ?? ({ id: i + 1 } as CoilStatus)),
    [coils],
  );

  // Yetenek: bipolar sürülebilen bobinler. Backend `bipolarYetenek` gönderir; gelmediyse
  // (eski backend) yedek kural bobin 1-5 → yanlış tarafa düşmemek için KISITLAYICI değil
  // üretim gerçeğiyle aynı varsayılan.
  const bipolarYetenek = useCallback(
    (c: CoilStatus) => (typeof c.bipolarYetenek === "boolean" ? c.bipolarYetenek : c.id <= 5),
    [],
  );

  // Kullanıcı isteği. Başlangıç: yeteneksiz bobinler unipolar, yetenekli olanlar bipolar
  // (firmware varsayılanı da budur — `istenen maske = 0`).
  const [istek, setIstek] = useState<boolean[]>(() =>
    Array.from({ length: STM_BOBIN }, (_, i) => (coils.find((c) => c.id === i + 1)?.bipolarYetenek ?? i < 5) === false),
  );
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [durum, setDurum] = useState<string | null>(null);

  const gonder = useCallback(
    async (yeni: boolean[]) => {
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
          setDurum("Kaydedildi — bir sonraki başlatmada uygulanır.");
        } else {
          // ⚠️ Başarısızlık SESSİZ KALMAZ: istek geri alınmaz ama kullanıcı kipin
          // gitmediğini görür, yoksa arayüz "bipolar" gösterirken kart unipolar sürer.
          setDurum("Gönderilemedi — kip DEĞİŞMEDİ.");
        }
      } catch {
        setDurum("Gönderilemedi — kip DEĞİŞMEDİ.");
      } finally {
        setGonderiliyor(false);
      }
    },
    [],
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

  return (
    <View style={styles.kok}>
      <Text style={styles.baslik}>⚡ Sürüş Kipi</Text>
      <Text style={styles.altBaslik}>
        Bipolar = iki PWM dönüşümlü (alan ±B) · Unipolar = yalnız IN_A (alan 0…+B)
      </Text>

      <View style={styles.hepsiSatir}>
        <TouchableOpacity
          style={[styles.hepsiBtn, kilitli && styles.pasif]}
          onPress={() => hepsi(false)}
          disabled={kilitli}
          accessibilityRole="button"
          accessibilityLabel="Yetenekli tüm bobinleri bipolar sür"
        >
          <Text style={styles.hepsiMetin}>Hepsi Bipolar</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.hepsiBtn, kilitli && styles.pasif]}
          onPress={() => hepsi(true)}
          disabled={kilitli}
          accessibilityRole="button"
          accessibilityLabel="Tüm bobinleri unipolar sür"
        >
          <Text style={styles.hepsiMetin}>Hepsi Unipolar</Text>
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
                `Bobin ${c.id}, ${uni ? "unipolar" : "bipolar"}` +
                (yetenekli ? "" : ", sürücüsü yalnız unipolar — değiştirilemez") +
                (etkin === null ? ", kart henüz bildirmedi" : `, kartın uyguladığı ${etkin ? "unipolar" : "bipolar"}`)
              }
            >
              <Text style={styles.kutuNo}>{c.id}</Text>
              <Text style={styles.kutuKip}>{uni ? "UNİ" : "BİP"}</Text>
              {!yetenekli && <Text style={styles.kutuKilit}>🔒</Text>}
            </TouchableOpacity>
          );
        })}
      </View>

      <Text style={styles.not}>
        🔒 Bobin 6-7 sürücüleri tek yönlü — bipolar sürülemez.
      </Text>
      {stmCoils.every((c) => typeof c.unipolar !== "boolean") ? (
        <Text style={styles.not}>Kartın uyguladığı kip sürüş başlayınca görünür.</Text>
      ) : (
        <Text style={styles.not}>
          Kartın uyguladığı:{" "}
          {stmCoils
            .map((c) => `${c.id}:${typeof c.unipolar === "boolean" ? (c.unipolar ? "UNİ" : "BİP") : "—"}`)
            .join("  ")}
        </Text>
      )}
      {durum && <Text style={[styles.not, styles.durum]}>{durum}</Text>}
      {!stmConnected && <Text style={[styles.not, styles.durum]}>STM32 bağlı değil — kip değiştirilemez.</Text>}
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
});
