// Author: mertaygn, cglrgrkn
/**
 * GA (istem 53) B3 — Ayarlar → "Geliştirici modülleri" anahtarı (Y299: satılan üründe varsayılan KAPALI; açmak sahip kararı).
 * Kapatınca sunucu etkin modülü BIRAKIR. ACİL DURDUR bu anahtardan BAĞIMSIZ olarak çalışan her modüle gider.
 */
import { useEffect, useState } from "react";
import { StyleSheet, Switch, Text, View } from "react-native";
import { useTranslation } from "react-i18next";
import { Card } from "@/components/ui/Card";
import { modulApi } from "@/services/moduller";
import { colors, rf, rs, spacing } from "@/theme/tokens";

export function GelistiriciModulleriKarti() {
  const { t } = useTranslation();
  const [gorunur, setGorunur] = useState<boolean | null>(null);
  const [hata, setHata] = useState(false);

  useEffect(() => {
    let canli = true;
    void modulApi.listele().then((r) => {
      if (canli) setGorunur(r.tamam ? r.veri.gorunur : false);
    });
    return () => {
      canli = false;
    };
  }, []);

  const degistir = async (deger: boolean) => {
    const r = await modulApi.gorunurlukYaz(deger);
    setHata(!r.tamam);
    if (r.tamam) setGorunur(r.veri.gorunur);
  };

  return (
    <Card style={styles.kart}>
      <View style={styles.satir}>
        <Text style={styles.baslik}>{t("ayarlar.gelistiriciModulleri.baslik")}</Text>
        <Switch
          value={gorunur === true}
          disabled={gorunur === null}
          onValueChange={(v) => void degistir(v)}
          accessibilityLabel={t("ayarlar.gelistiriciModulleri.anahtar")}
          testID="gelistirici-modulleri-anahtar"
        />
      </View>
      <Text style={styles.aciklama}>{t("ayarlar.gelistiriciModulleri.aciklama")}</Text>
      {hata && (
        <Text style={styles.hata} testID="gelistirici-modulleri-hata">
          {t("ayarlar.gelistiriciModulleri.hata")}
        </Text>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  kart: { gap: rs(8), marginTop: spacing.md },
  satir: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  baslik: { flex: 1, color: colors.text, fontSize: rf(15), fontWeight: "700" },
  aciklama: { color: colors.textMuted, fontSize: rf(12) },
  hata: { color: colors.warning, fontSize: rf(12), fontWeight: "700" },
});
