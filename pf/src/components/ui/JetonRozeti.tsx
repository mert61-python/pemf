// Author: mertaygn
/**
 * JETON ROZETİ — üst barda kalan analiz hakkı (sahip isteği 2026-09-13:
 * "kullanıcı da kalan hakkını görmeli").
 *
 * ⚠️ ÜCRETLENDİRME KAPALIYKEN HİÇBİR ŞEY ÇİZMEZ. Bugün canlıda `PEMF_JETON_ENFORCED=0`;
 * rozet "0" deseydi operatör hakkının bittiğini sanardı (sınırsız çalışırken). Karar
 * backend'den gelir (`etkin:false`), arayüz tahmin ETMEZ.
 *
 * ⚠️ OKUNAMADIĞINDA "—" — 0 DEĞİL. Bakiye Supabase'den okunur; internetsiz klinikte okuma
 * düşer ve o an 0 yazmak çalışan sistemi bitmiş gibi gösterir.
 */
import { useCallback, useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Coins } from "lucide-react-native";
import { colors, radius, rf, rs, spacing, touch, typography } from "@/theme/tokens";
import { emitToast } from "@/services/toastBridge";
import {
  bakiyeDurumu,
  bakiyeMetni,
  jetonBakiyesiGetir,
  JETON_KAPALI,
  type JetonBakiyesi,
} from "@/services/jetonBakiye";

/** Rozet kendi kendine tazelenir; analiz sonrası sayı elle yenilenmeden düşsün. */
const TAZELEME_MS = 60_000;

/**
 * Ücretlendirme KAPALIYKEN yoklama aralığı.
 *
 * ⚠️ İlk yazımda tek aralık vardı ve rozet, özellik kapalı olsa bile ömür boyu dakikada bir
 * istek atıyordu. Bugün canlıda `PEMF_JETON_ENFORCED=0`, yani bu **her klinikte** boşa giden
 * bir yoklamaydı (uygulama günlerce açık kalıyor — 24 saatte ~1440 istek, hepsi aynı
 * `{etkin:false}` cevabı için).
 *
 * ⚠️ Neden TAMAMEN durdurmuyoruz: ücretlendirme sonradan açılırsa (backend yeniden başlatılır)
 * açık duran istemci bunu bir daha ASLA fark etmezdi ve kullanıcı bakiyesini göremezdi.
 * 10 dakika, boşa yoklamayı 10 kat azaltırken kendiliğinden toparlamayı korur.
 */
const KAPALI_TAZELEME_MS = 600_000;

export function JetonRozeti({ kompakt = false }: { kompakt?: boolean }) {
  const [bakiye, setBakiye] = useState<JetonBakiyesi>(JETON_KAPALI);

  const tazele = useCallback(async () => {
    try {
      setBakiye(await jetonBakiyesiGetir());
    } catch {
      // jetonBakiyesiGetir zaten `silent`; buraya düşmesi beklenmez.
      setBakiye(JETON_KAPALI);
    }
  }, []);

  // Aralık, öğrenilen duruma göre: açıkken 1 dk, kapalıyken 10 dk (bkz. KAPALI_TAZELEME_MS).
  const aralik = bakiye.etkin ? TAZELEME_MS : KAPALI_TAZELEME_MS;
  useEffect(() => {
    tazele();
    const id = setInterval(tazele, aralik);
    return () => clearInterval(id);
  }, [tazele, aralik]);

  const metin = bakiyeMetni(bakiye);
  // ⚠️ Ücretlendirme kapalıysa `metin` null döner → HİÇBİR ŞEY çizilmez (boş kutu bile yok).
  if (metin === null) return null;

  const durum = bakiyeDurumu(bakiye);
  const renk =
    durum === "bitti" ? colors.danger : durum === "az" ? colors.warning : colors.textMuted;

  const aciklama = () => {
    if (durum === "bilinmiyor") {
      emitToast(
        bakiye.sebep === "kimlik_yok"
          ? "Jeton bakiyesi için giriş yapmanız gerekiyor."
          : "Jeton bakiyesi okunamadı (çevrimdışı). Analiz yapmaya devam edebilirsiniz; " +
              "kullanım internet gelince uzlaşır.",
        "info",
      );
      return;
    }
    if (bakiye.odemeModeli === "kullandikca") {
      emitToast(`Faturalanmamış kullanım: ${bakiye.borc ?? 0} analiz.`, "info");
      return;
    }
    const m = bakiye.maliyet || {};
    emitToast(
      `Kalan analiz hakkı: ${bakiye.kalan}. ` +
        `Görüntü/ses ${m.goruntu ?? 1} · araştırma ${m.agir_arastirma ?? 3} · ` +
        `otonom seans ${m.ai_pro_seans ?? 5} jeton. ` +
        "Seans ve acil durdurma jetondan etkilenmez.",
      durum === "bitti" ? "error" : "info",
    );
  };

  return (
    <Pressable
      onPress={aciklama}
      style={[styles.kutu, durum === "bitti" && styles.kutuBitti, durum === "az" && styles.kutuAz]}
      accessibilityRole="button"
      accessibilityLabel={`Kalan jeton: ${metin}. Ayrıntı için dokunun.`}
    >
      <Coins size={14} color={renk} />
      <Text style={[styles.metin, { color: renk }]} numberOfLines={1}>
        {metin}
      </Text>
      {!kompakt && (
        <Text style={styles.etiket} numberOfLines={1}>
          jeton
        </Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  kutu: {
    flexDirection: "row",
    alignItems: "center",
    gap: rs(5),
    paddingHorizontal: spacing.sm,
    // a11y: dokunma hedefi en az 44 px. ⚠️ rs(44) DEĞİL —  ölçekle küçülür ve
    // 0,85 katsayısında 37 px'e düşer (dokunma-hedefi kapısı bunu yakaladı).
    // taban koyar: Math.max(44, rs(44)).
    minHeight: touch.min,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.panel,
  },
  kutuAz: { borderColor: colors.warning },
  kutuBitti: { borderColor: colors.danger },
  metin: { fontSize: typography.small, fontWeight: "700", fontVariant: ["tabular-nums"] },
  // ⚠️ rf(10) DEĞİL: 9-10 punto okunmuyor ve yazı-ölçeği çırcırı onu reddediyor
  // (tests/test_arayuz_yazi_olcegi_kapisi.py). Taban punto  (11).
  etiket: { fontSize: typography.small, color: colors.textMuted },
});
