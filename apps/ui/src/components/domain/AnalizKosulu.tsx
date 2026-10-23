// Author: mertaygn, cglrgrkn
/**
 * ANALİZ KOŞULU + KABİN KAMERASI (T3 · Y189, sahip + Çağlar Hoca 2026-10-23).
 *
 * `KosulSecici` — "Koşullu | Koşulsuz": "engelleri tamamen kaldırdığın bir sürüm, butonla kontrol edilebilir; AI tek başına ne
 * bulacak". Petri / fantom analizinde ve AI Pro'da (araştırma modelleri) AYNI bileşen. Varsayılan KOŞULLU, seçim HATIRLANMAZ
 * (her açılışta koşullu). Kural backend'dedir (`ai_hub/cv_ortak/pemf_kapisi.py` + petri v2 hattı): koşulsuzda engeller analizi /
 * sürüşü KESMEZ, uyarı olarak gösterilir; kabin çerçevesinde konum yoksa yine sürülmez. Bileşen yalnız seçimi taşır.
 *
 * `KabinKaresiDugmesi` — "Kabin kamerasından çek": analizin görüntüsünü tarayıcının / WebView'in VARSAYILAN kamerasından (dizüstünün
 * kendi kamerası) DEĞİL, Ayarlar ▸ Kabin kamerası'nda seçilen kameradan 1920×1080 alır (`POST /api/settings/kabin-kamerasi/kare`;
 * kalibrasyonla aynı çözünürlük). Kamera backend'in makinesindedir → düğme yalnız backend bu makinedeyken görünür.
 */
import React, { useState } from "react";
import { ActivityIndicator, Text, TouchableOpacity, View } from "react-native";
import { Video } from "lucide-react-native";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/ToastProvider";
import { authHeaders } from "@/services/apiClient";
import { backendBuMakinede } from "@/services/backendKonumu";
import { serviceConfig } from "@/services/config";
import { colors, touch, typography } from "@/theme/tokens";
import { aiDetayCumlesi } from "@/utils/aiHataDetayi";

export function KosulSecici({
  kosulsuz,
  onDegis,
  kilitli = false,
  testID = "kosul-secici",
}: {
  kosulsuz: boolean;
  onDegis: (kosulsuz: boolean) => void;
  kilitli?: boolean;
  testID?: string;
}) {
  const { t } = useTranslation();
  const secenekler: [boolean, string][] = [
    [false, t("ai.kosul.kosullu")],
    [true, t("ai.kosul.kosulsuz")],
  ];
  return (
    <View testID={testID} style={{ marginVertical: 6 }}>
      <View style={{ flexDirection: "row", gap: 8 }} accessibilityRole="radiogroup" accessibilityLabel={t("ai.kosul.etiket")}>
        {secenekler.map(([deger, etiket]) => {
          const secili = kosulsuz === deger;
          return (
            <TouchableOpacity
              key={String(deger)}
              testID={deger ? `${testID}-kosulsuz` : `${testID}-kosullu`}
              disabled={kilitli}
              onPress={() => onDegis(deger)}
              accessibilityRole="radio"
              accessibilityState={{ selected: secili, disabled: kilitli }}
              accessibilityLabel={etiket}
              style={{
                flex: 1,
                minHeight: touch.sm,
                justifyContent: "center",
                padding: 8,
                borderWidth: 1,
                borderRadius: 8,
                borderColor: secili ? (deger ? colors.warning : colors.primary) : colors.border,
                opacity: kilitli ? 0.5 : 1,
              }}
            >
              <Text style={{ fontSize: typography.small, fontWeight: secili ? "bold" : "normal", color: colors.text }}>
                {secili ? "◉" : "○"} {etiket}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
      <Text
        testID={`${testID}-aciklama`}
        style={{ fontSize: typography.small, marginTop: 4, color: kosulsuz ? colors.warning : colors.textMuted }}
      >
        {kosulsuz ? t("ai.kosul.kosulsuzUyari") : t("ai.kosul.kosulluAciklama")}
      </Text>
    </View>
  );
}

export function KabinKaresiDugmesi({ onKare }: { onKare: (base64: string) => void }) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const [cekiyor, setCekiyor] = useState(false);
  if (!backendBuMakinede()) return null;
  const cek = async () => {
    setCekiyor(true);
    try {
      const r = await fetch(serviceConfig.apiBaseUrl + "/settings/kabin-kamerasi/kare", {
        method: "POST",
        headers: { Accept: "application/json", ...authHeaders() },
      });
      const j = await r.json().catch(() => null);
      if (r.ok && j?.image_base64) onKare(String(j.image_base64));
      else showToast(aiDetayCumlesi(j?.detail, t("ai.kabinKamerasi.hata")), "error");
    } catch {
      showToast(t("ai.kabinKamerasi.hata"), "error");
    } finally {
      setCekiyor(false);
    }
  };
  return (
    <View testID="kabin-karesi-dugmesi" style={{ width: "100%", marginTop: 6 }}>
      <Button
        label={cekiyor ? t("ai.kabinKamerasi.cekiliyor") : t("ai.kabinKamerasi.cek")}
        icon={cekiyor ? <ActivityIndicator color={colors.white} /> : <Video color={colors.white} size={16} />}
        disabled={cekiyor}
        onPress={cek}
      />
    </View>
  );
}
