// Author: mertaygn, cglrgrkn
/**
 * PEMF TÜKETİM KAPISI KUTUSU — hocanın petri v2 / fantom v3 sonucunun bobin sürüşüne ESAS ALINIP ALINAMAYACAĞINI söyler
 * (AI-2, 2026-10-12). Metinler BACKEND'den gelir (`pemf_kapisi`, tek kaynak `ai_hub/cv_ortak/pemf_kapisi.py`): gömülü uç ve
 * GPU servisi aynı metni üretir; arayüz kural UYDURMAZ, yalnız gösterir.
 *
 * Gösterilen:
 *  · rozetler — "PEMF girdisi geçerli / GEÇERSİZ", fantomda "tespit güvenilir / güvenilir DEĞİL";
 *  · kapı geçmezse EYLEM metinleri (ör. "PEMF değerleri geçersiz: plakanın kabindeki konumu bilinmiyor — kabine ArUco koyun
 *    ya da konumu ayarlayın."; `oblique_view` / `low_resolution` / `ring_partial` → "yeniden çekin");
 *  · laboratuvar VARSAYIMLARI (CST kutusu eksen işareti, halka çapı, A1 köşesi, kontrol kuyucuğu yoksa kanser eşikleri).
 * ⚠️ Eski backend `pemf_kapisi` göndermez → bileşen HİÇBİR ŞEY çizmez (çökmez, uydurmaz).
 */
import React from "react";
import { Text, View } from "react-native";

import { colors, typography } from "@/theme/tokens";

export interface PemfKapisi {
  surulebilir?: boolean;
  pemf_gecerli?: boolean;
  nedenler?: string[];
  eylem?: string;
  mesajlar?: { kod: string; metin: string }[];
  varsayimlar?: { kod: string; metin: string }[];
}

export function PemfKapisiKutusu({
  kapi,
  reliable,
  model,
}: {
  kapi?: PemfKapisi | null;
  reliable?: boolean | null;
  model: "petri" | "fantom";
}) {
  if (!kapi || typeof kapi !== "object") return null;
  const mesajlar = Array.isArray(kapi.mesajlar) ? kapi.mesajlar : [];
  const varsayimlar = Array.isArray(kapi.varsayimlar) ? kapi.varsayimlar : [];
  const gecerli = kapi.pemf_gecerli === true;
  const surulebilir = kapi.surulebilir === true;
  return (
    <View
      testID="pemf-kapisi"
      accessibilityRole="summary"
      style={{
        borderWidth: 1,
        borderColor: surulebilir ? colors.border : colors.danger,
        borderRadius: 8,
        padding: 8,
        marginVertical: 6,
        backgroundColor: surulebilir ? "transparent" : "rgba(220,38,38,0.06)",
      }}
    >
      {/* AII-3.9: başlık kutunun HÜKMÜNÜ söyler — kabin çerçevesi geçerli ama engelleyici neden varsa YEŞİL "✔ geçerli" yazılmaz
          (kırmızı "ESAS ALINMAZ" ile çelişiyordu; göz ilk satırı okur). */}
      <Text style={{ fontSize: typography.small, fontWeight: "bold", color: surulebilir ? colors.success : colors.danger }}>
        {surulebilir
          ? "✔ PEMF girdisi geçerli"
          : gecerli
            ? "⛔ Sonuç bobin sürüşüne KULLANILAMAZ (kabin konumu geçerli — nedenler aşağıda)"
            : "⛔ PEMF girdisi GEÇERSİZ"}
        {model === "fantom" && reliable != null ? (
          <Text style={{ color: !reliable ? colors.danger : surulebilir ? colors.success : colors.textMuted }}>
            {!reliable ? "   ·   ⛔ tespit güvenilir DEĞİL" : surulebilir ? "   ·   ✔ tespit güvenilir" : "   ·   tespit güvenilir"}
          </Text>
        ) : null}
      </Text>
      {!surulebilir ? (
        <Text style={{ fontSize: typography.small, color: colors.text, marginTop: 4 }}>
          Aşağıdaki D / P / E değerleri bobin sürüşüne ESAS ALINMAZ:
        </Text>
      ) : null}
      {mesajlar.map((m) => (
        <Text key={m.kod} testID={`pemf-kapisi-${m.kod}`} style={{ fontSize: typography.small, color: colors.danger, marginTop: 2 }}>
          • {m.metin}
        </Text>
      ))}
      {varsayimlar.map((v) => (
        <Text key={v.kod} testID={`pemf-varsayim-${v.kod}`} style={{ fontSize: typography.small, color: colors.textMuted, marginTop: 2 }}>
          ⚠ {v.metin}
        </Text>
      ))}
    </View>
  );
}
