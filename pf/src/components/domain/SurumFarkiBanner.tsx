// Author: mertaygn, cglrgrkn
/**
 * SÜRÜM BANDI (sahip kararı 2026-08-22; SAHADA DÜZELTİLDİ 2026-08-23).
 *
 * ⚠️ İLK TASARIM HATASI (kullanıcı bildirdi): bant telefonun 2.3.x sürümünü CİHAZIN 1.9.x
 * sürümüyle kıyaslıyordu. İki ayrı numaralandırma şeması hiçbir zaman eşit olamaz — bant TAM
 * GÜNCEL sistemde de "Sürümler farklı" diyordu. Sürekli yanlış alarm, gerçek uyarının değerini
 * sıfırlar. DOĞRU ÖLÇÜ: yayınlanmış en son MOBİL sürüm — güncelleme altyapısıyla
 * (`guncellemeVarMi`) aynı kaynak. Cihaz sürümüyle kıyas GERİ EKLENMEZ.
 *
 * NEDEN VAR. Telefon, cihazdan bağımsız olarak eski sürümde KALABİLİR ve bu kasıtlıdır:
 * Android'de kurulumu işletim sistemi sorar; kullanıcı erteleyebilir. Güncelleme ZORUNLU
 * KILINAMAZ ve bağlantı sürüm farkında ASLA reddedilmez — bir tıbbi cihazın uzaktan ACİL
 * DURDURMASINI sürüm eşleşmesine bağlamak kabul edilemez (bkz. MobileUpdateGate). Ama "sessizce
 * eksik" de kabul edilemez: bu sürümde eklenen düzeltmelerin bir kısmı İSTEMCİ tarafındadır ve
 * eski telefonda YOKTUR. Bant, kapıda ertelenen güncellemeyi içeride görünür tutar.
 *
 * İŞ BÖLÜMÜ (çift bant olmaz — ortak ölçü `atlandiMi`, aynı modül durumu):
 *   · erteleme YOK  → MobileUpdateBanner sahnede (indirme düğmeli) — bu bant SUSAR;
 *   · kapıda ERTELENDİ → MobileUpdateBanner susar — bu bant hatırlatır (hafif, kapatılabilir).
 *
 * ⚠️ HASTA GÜVENLİĞİ: donanım çalışırken GÖSTERİLMEZ (RecoveryCodeBanner ilkesi). Ölçü
 * `useDonanimCalisiyor` — seans kaydı açık olmasa da çalışan bobin susturur.
 * ⚠️ FAIL-QUIET: ağ/manifest yoksa bant YOK — internetsiz klinikte sahte uyarı üretilmez.
 */
import { useEffect, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Info, X } from "lucide-react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { useDonanimCalisiyor } from "@/hooks/useDonanimCalisiyor";
import { atlandiMi, guncellemeVarMi, mevcutVersionCode, type MobilSurum } from "@/services/mobileUpdate";
import { colors, radius, rf, rs, spacing } from "@/theme/tokens";

/** Kapatma, GÖRÜLEN sürüm çiftine bağlıdır: yeni bir yayın çıkınca bant yeniden görünür. */
const ANAHTAR = "pemf.surumFarki.kapatilan";

function uygulamaSurumu(): string {
  try {
    // @ts-ignore - expo-constants opsiyonel
    return require("expo-constants").default?.expoConfig?.version || "";
  } catch {
    return "";
  }
}

export function SurumFarkiBanner() {
  const donanimCalisiyor = useDonanimCalisiyor();
  const [surum, setSurum] = useState<MobilSurum | null>(null);
  const [kapatilan, setKapatilan] = useState<string | null>(null);
  const [yuklendi, setYuklendi] = useState(false);

  useEffect(() => {
    let iptal = false;
    void (async () => {
      // İkisi de fail-quiet: okunamazsa "güncelleme yok / kapatılmamış" varsayılır.
      const [durum, kayit] = await Promise.all([
        guncellemeVarMi().catch(() => ({ varMi: false as const })),
        AsyncStorage.getItem(ANAHTAR).catch(() => null),
      ]);
      if (iptal) return;
      if (durum.varMi && durum.surum) setSurum(durum.surum);
      setKapatilan(kayit);
      setYuklendi(true);
    })();
    return () => {
      iptal = true;
    };
  }, []);

  // Güncel ya da bilinemiyor → SESSİZ. (Sahadaki yanlış alarmın kilidi: "fark" ölçüsü artık
  // yalnızca yayınlanmış son mobil sürümdür, cihazın 1.9.x sürümü değil.)
  if (!yuklendi || !surum) return null;
  // Erteleme yoksa güncelleme bandı (indirme düğmeli) zaten sahnede — aynı şeyi iki kez söyleme.
  if (!atlandiMi(surum.versionCode)) return null;
  if (donanimCalisiyor) return null;

  const cift = `${mevcutVersionCode()}|${surum.versionCode}`;
  if (kapatilan === cift) return null;

  return (
    <View style={s.kutu}>
      <Info size={rs(16)} color={colors.primary} />
      <View style={s.metin}>
        <Text style={s.baslik}>
          Telefon sürümü eski: {uygulamaSurumu() || "bu sürüm"} → {surum.version}
        </Text>
        <Text style={s.aciklama}>
          Bağlantı ve acil durdurma normal çalışır; ancak bu telefonda bazı düzeltmeler ve
          uyarılar eksik olabilir. Güncelleme, uygulama yeniden açıldığında tekrar önerilecek.
        </Text>
      </View>
      <TouchableOpacity
        onPress={() => {
          setKapatilan(cift);
          AsyncStorage.setItem(ANAHTAR, cift).catch(() => {});
        }}
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        accessibilityLabel="Sürüm bildirimini kapat"
      >
        <X size={rs(16)} color={colors.textMuted} />
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  kutu: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    marginHorizontal: spacing.md,
    marginTop: spacing.sm,
    padding: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.panelSoft,
    borderWidth: 1,
    borderColor: colors.border,
  },
  metin: { flex: 1 },
  baslik: { color: colors.text, fontSize: rf(13), fontWeight: "600" },
  aciklama: { color: colors.textMuted, fontSize: rf(11), marginTop: 2, lineHeight: rf(15) },
});
